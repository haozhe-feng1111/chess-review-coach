"""Explorer contract, OAuth binding, caching and upstream failure isolation."""

import base64
import hashlib
import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from urllib.parse import parse_qs, urlparse

import chess
import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from api.lichess import auth, explorer, router
from config import settings
from explorer.auth import LichessAuth
from explorer.client import LichessExplorer, cache_key, retry_delay
from models.explorer import ExplorerQuery
from storage.db import Database
from storage.models import ExplorerCacheEntry

PAYLOAD = {"white": 60, "draws": 10, "black": 30, "moves": [
    {"uci": "e2e4", "san": "untrusted", "white": 30, "draws": 5, "black": 15, "averageRating": 1500},
]}


@pytest.fixture
def db(tmp_path):
    database = Database("sqlite:///" + (tmp_path / "explorer.db").as_posix())
    database.create_all()
    yield database
    database.dispose()


def query(**kwargs):
    return ExplorerQuery(fen=chess.STARTING_FEN, **kwargs)


def service(db, tmp_path, handler, token="test-token"):
    account = LichessAuth(tmp_path / "token.json", token)
    return LichessExplorer(db, account, transport=httpx.MockTransport(handler))


def test_historical_outcomes_and_request_minimization(db, tmp_path):
    calls = []
    def handler(request):
        calls.append(request)
        assert request.url.host == "explorer.lichess.org"
        assert request.headers["authorization"] == "Bearer test-token"
        assert request.url.params["ratings"] == "1200,1400,1600"
        assert request.url.params["speeds"] == "rapid"
        assert request.url.params["topGames"] == request.url.params["recentGames"] == "0"
        assert request.url.params["since"] == "2020-01"
        assert "pgn" not in request.url.params
        return httpx.Response(200, json=PAYLOAD)
    client = service(db, tmp_path, handler)
    first = client.query(query(since="2020-01"))
    second = client.query(query(since="2020-01"))
    assert first.status == "ok" and not first.cached and second.cached
    assert first.data.white == 60 and first.data.black == 30
    assert first.data.moves[0].san == "e4"
    assert "test-token" not in first.model_dump_json()
    assert len(calls) == 1


def test_simultaneous_identical_queries_make_one_upstream_call(db, tmp_path):
    calls = []
    def handler(request):
        calls.append(request)
        time.sleep(0.02)
        return httpx.Response(200, json=PAYLOAD)
    client = service(db, tmp_path, handler)
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(lambda _: client.query(query()), range(3)))
    assert all(result.status == "ok" for result in results)
    assert len(calls) == 1


def test_cache_persists_without_token_but_expires(db, tmp_path):
    client = service(db, tmp_path, lambda _: httpx.Response(200, json=PAYLOAD))
    client.query(query())
    offline = service(db, tmp_path, lambda _: pytest.fail("no network"), token="")
    assert offline.query(query()).cached
    with db.session() as session:
        session.get(ExplorerCacheEntry, cache_key(query())).fetched_at = datetime.utcnow() - timedelta(days=2)
    assert offline.query(query()).status == "auth_required"


def test_cache_key_includes_filters_and_position_not_move_counters():
    root = query()
    counter = root.model_copy(update={"fen": chess.STARTING_FEN.replace("0 1", "12 9")})
    assert cache_key(root) == cache_key(counter)
    for changed in (query(ratings=[1800]), query(speeds=["blitz"]), query(since="2024-01"), query(until="2025-01")):
        assert cache_key(root) != cache_key(changed)
    board = chess.Board(); board.push_uci("e2e4")
    assert cache_key(root) != cache_key(ExplorerQuery(fen=board.fen()))


@pytest.mark.parametrize("changes", [
    {"fen": "nonsense"}, {"fen": "8/8/8/8/8/8/8/8 w - - 0 1"}, {"ratings": [1700]},
    {"ratings": []}, {"speeds": ["unknown"]}, {"speeds": []},
    {"since": "2024-13"}, {"since": "2025-02", "until": "2024-12"},
])
def test_rejects_invalid_queries(changes):
    with pytest.raises(ValidationError):
        ExplorerQuery.model_validate({"fen": chess.STARTING_FEN, **changes})


@pytest.mark.parametrize("status,expected", [(401, "auth_required"), (403, "auth_required"), (500, "unavailable")])
def test_errors_never_become_zero_games_or_cached(db, tmp_path, status, expected):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(status, text="private upstream body")
    client = service(db, tmp_path, handler)
    for _ in range(2):
        result = client.query(query())
        assert result.status == expected and result.data is None
        assert "private" not in result.model_dump_json()
    assert len(calls) == 2


def test_rate_limit_is_shared_across_positions_and_honors_retry_after(db, tmp_path):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(429, headers={"Retry-After": "120"})
    client = service(db, tmp_path, handler)
    assert client.query(query()).retry_after == 120
    limited = client.query(query(ratings=[2200]))
    assert limited.status == "rate_limited" and limited.retry_after > 60
    assert len(calls) == 1
    assert retry_delay("1") == retry_delay("invalid") == 60


@pytest.mark.parametrize("payload", [
    [], {}, {**PAYLOAD, "white": -1}, {**PAYLOAD, "white": "60"},
    {**PAYLOAD, "moves": [{**PAYLOAD["moves"][0], "uci": "e2e5"}]},
    {**PAYLOAD, "moves": [{**PAYLOAD["moves"][0], "white": 100}]},
    {**PAYLOAD, "moves": [None]}, {**PAYLOAD, "moves": PAYLOAD["moves"] * 2},
])
def test_malformed_upstream_fails_closed(db, tmp_path, payload):
    client = service(db, tmp_path, lambda _: httpx.Response(200, json=payload))
    result = client.query(query())
    assert result.status == "unavailable" and result.data is None


def test_timeout_and_empty_sample_are_distinct(db, tmp_path):
    def timeout(request):
        raise httpx.ReadTimeout("private", request=request)
    assert service(db, tmp_path, timeout).query(query()).status == "unavailable"
    empty = {"white": 0, "draws": 0, "black": 0, "moves": []}
    result = service(db, tmp_path, lambda _: httpx.Response(200, json=empty)).query(query())
    assert result.status == "ok" and result.data.white == 0


def test_oauth_pkce_state_single_use_and_private_storage(tmp_path):
    def exchange(request):
        form = parse_qs(request.content.decode())
        challenge = base64.urlsafe_b64encode(hashlib.sha256(form["code_verifier"][0].encode()).digest()).rstrip(b"=").decode()
        assert challenge == params["code_challenge"][0]
        assert form["redirect_uri"] == [callback]
        assert "client_secret" not in form
        return httpx.Response(200, json={"access_token": "secret-for-test", "token_type": "Bearer", "expires_in": 3600})
    account = LichessAuth(tmp_path / "token.json", transport=httpx.MockTransport(exchange))
    callback = "http://127.0.0.1:8000/api/lichess/callback"
    state, url = account.begin(callback, "ExampleAccount")
    params = parse_qs(urlparse(url).query)
    assert params["code_challenge_method"] == ["S256"] and "scope" not in params
    with pytest.raises(ValueError):
        account.finish(state, "wrong-browser", "code")
    assert not account.token()
    account.finish(state, state, "code")
    assert account.token() == "secret-for-test"
    with pytest.raises(ValueError):
        account.finish(state, state, "code")
    account.disconnect()
    assert not account.token()


def test_expired_or_corrupt_credentials_are_not_connected(tmp_path):
    account = LichessAuth(tmp_path / "token.json")
    for data in ([], {"access_token": "old", "expires_at": 1}, {"expires_at": "bad"}):
        account.token_file.write_text(json.dumps(data), encoding="utf-8")
        assert account.token() == ""
    state, _ = account.begin("http://localhost/callback")
    verifier, callback, _ = account._pending[state]
    account._pending[state] = (verifier, callback, 1)
    with pytest.raises(ValueError):
        account.finish(state, state, "code")


def test_api_exposes_status_not_credentials_and_checks_origin(db, tmp_path):
    account = LichessAuth(tmp_path / "token.json")
    app = FastAPI(); app.include_router(router)
    app.dependency_overrides[auth] = lambda: account
    app.dependency_overrides[explorer] = lambda: LichessExplorer(db, account)
    with TestClient(app, base_url="http://127.0.0.1:8000") as client:
        assert client.get("/api/lichess/status").json() == {"connected": False, "configured_by_environment": False}
        connection = client.get("/api/lichess/connect", follow_redirects=False)
        assert connection.status_code == 302
        assert "HttpOnly" in connection.headers["set-cookie"]
        assert connection.headers["cache-control"] == "no-store"
        denied = client.get("/api/lichess/callback?state=wrong&code=never-show-this")
        assert denied.status_code == 400 and "never-show-this" not in denied.text
        assert client.delete("/api/lichess/connection", headers={"origin": "https://foreign.example"}).status_code == 403
        assert client.delete("/api/lichess/connection", headers={"origin": settings.cors_origin_list[0]}).status_code == 200
        assert client.post("/api/lichess/explorer", json={"fen": "broken"}).status_code == 422
        assert client.post("/api/lichess/explorer", json=query().model_dump()).json()["status"] == "auth_required"
    with TestClient(app, base_url="http://foreign.example") as client:
        assert client.get("/api/lichess/connect", follow_redirects=False).status_code == 400
