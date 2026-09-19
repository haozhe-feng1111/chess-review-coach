"""Exercise real UCI limits/cancellation and persistence without using the user's DB."""

import io
import time
from types import SimpleNamespace

import chess
import chess.pgn
import pytest
from fastapi.testclient import TestClient

from analysis.study import initial_study, validate_study, export_study
from api.main import create_app
from api.service import get_service
from engine.live import LiveAnalysis, search_board
from models.workbench import SaveStudy, SearchSettings, StartSearch
from storage.models import Game, Study
from storage.repository import delete_game


def game_from_pgn(pgn="1. e4 e5 2. Nf3 Nc6 *", game_id="workbench-test"):
    parsed = chess.pgn.read_game(io.StringIO(pgn))
    board = parsed.board()
    moves = []
    for move in parsed.mainline_moves():
        before = board.fen()
        board.push(move)
        moves.append({"uci": move.uci(), "fen_before": before, "fen_after": board.fen()})
    return Game(id=game_id, pgn=pgn, headers=dict(parsed.headers), result=parsed.headers["Result"], review_json={"moves": moves})


def payload(study, **changes):
    return SaveStudy(revision=study["revision"], selected_id=changes.get("selected_id", study["selected_id"]),
                     moves=changes.get("moves", [{k: n[k] for k in ("id", "parent_id", "uci")} for n in study["nodes"][1:]]))


def test_nested_variations_export_and_original_line_preserved():
    game = game_from_pgn()
    study = initial_study(game)
    moves = payload(study).model_dump()["moves"] + [
        {"id": "v1", "parent_id": "m1", "uci": "c7c5"},
        {"id": "v2", "parent_id": "v1", "uci": "g1f3"},
        {"id": "v3", "parent_id": "v1", "uci": "b1c3"},
    ]
    saved = validate_study(game, payload(study, moves=moves, selected_id="v3"))
    parsed = chess.pgn.read_game(io.StringIO(export_study(game, saved)))
    assert [m.uci() for m in parsed.mainline_moves()] == ["e2e4", "e7e5", "g1f3", "b8c6"]
    branch = parsed.variations[0].variations[1]
    assert branch.san() == "c5"
    assert [n.san() for n in branch.variations] == ["Nf3", "Nc3"]
    assert saved["nodes"][-1]["original_ply"] is None


def test_imported_pgn_variations_survive():
    study = initial_study(game_from_pgn("1. e4 (1. d4 d5) e5 (1... c5 2. Nf3) 2. Nf3 *"))
    assert len(study["nodes"]) == 8
    assert [n["san"] for n in study["nodes"] if n["original_ply"]] == ["e4", "e5", "Nf3"]


@pytest.mark.parametrize("extra", [
    {"id": "v1", "parent_id": "m1", "uci": "e7e4"},
    {"id": "v1", "parent_id": "missing", "uci": "e7e5"},
    {"id": "m1", "parent_id": "root", "uci": "d2d4"},
    {"id": "v1", "parent_id": "root", "uci": "e2e4"},
])
def test_illegal_or_ambiguous_studies_rejected(extra):
    game = game_from_pgn()
    study = initial_study(game)
    with pytest.raises(ValueError):
        validate_study(game, payload(study, moves=payload(study).model_dump()["moves"] + [extra]))


def test_cannot_remove_original_move():
    game = game_from_pgn()
    study = initial_study(game)
    with pytest.raises(ValueError, match="实战主线"):
        validate_study(game, payload(study, moves=payload(study).model_dump()["moves"][:-1]))


@pytest.mark.parametrize("fen,uci,san", [
    ("r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1", "e1g1", "O-O"),
    ("4k3/8/8/3pP3/8/8/8/4K3 w - d6 0 2", "e5d6", "exd6"),
    ("4k3/P7/8/8/8/8/8/4K3 w - - 0 1", "a7a8n", "a8=N"),
])
def test_special_moves(fen, uci, san):
    game = game_from_pgn(f'[SetUp "1"]\n[FEN "{fen}"]\n\n*')
    study = initial_study(game)
    saved = validate_study(game, payload(study, moves=[{"id": "v1", "parent_id": "root", "uci": uci}], selected_id="v1"))
    assert saved["nodes"][-1]["san"] == san


def test_revision_conflict_refresh_and_delete(temp_database):
    with temp_database.session() as session:
        session.add(game_from_pgn())
    app = create_app()
    app.dependency_overrides[get_service] = lambda: SimpleNamespace(database=temp_database)
    client = TestClient(app)
    url = "/api/games/workbench-test/study"
    original = client.get(url).json()
    body = payload(original).model_dump()
    body["moves"].append({"id": "v1", "parent_id": "m1", "uci": "c7c5"})
    body["selected_id"] = "v1"
    first = client.put(url, json=body)
    assert first.status_code == 200
    assert first.json()["revision"] == 1
    assert client.put(url, json=body).status_code == 409
    reopened = client.get(url).json()
    assert reopened["selected_id"] == "v1"
    assert reopened["nodes"][-1]["san"] == "c5"
    body["revision"] = 1
    assert client.put(url, json=body).json()["revision"] == 2
    assert client.put(url, json=body).status_code == 409
    assert "c5" in client.get("/api/games/workbench-test/study.pgn").text
    # Replacing a review row, as force-analysis does, must not erase variations.
    with temp_database.session() as session:
        session.delete(session.get(Game, "workbench-test"))
        session.flush()
        session.add(game_from_pgn())
    assert client.get(url).json()["revision"] == 2
    with temp_database.session() as session:
        assert delete_game(session, "workbench-test")
    with temp_database.session() as session:
        assert session.get(Study, "workbench-test") is None


def test_move_history_is_sent_for_repetition():
    board = search_board(StartSearch(client_id="test", sequence=1, root_fen=chess.STARTING_FEN,
                                    moves=["g1f3", "g8f6", "f3g1", "f6g8"] * 2))
    assert board.is_repetition(3)
    with pytest.raises(ValueError):
        search_board(StartSearch(client_id="test", sequence=1, root_fen=chess.STARTING_FEN, moves=["e2e5"]))


def wait_job(manager, job_id, timeout=15):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        data = manager.read(job_id)
        if data["status"] not in ("queued", "running"):
            return data
        time.sleep(0.04)
    pytest.fail("Live analysis did not settle")


def test_real_engine_limits_multipv_resources_and_cancellation(engine_path):
    manager = LiveAnalysis(engine_path)
    try:
        request = StartSearch(client_id="test", sequence=1, root_fen=chess.STARTING_FEN,
                              settings=SearchSettings(mode="depth", depth=8, threads=1, hash_mb=16, multipv=3))
        first = wait_job(manager, manager.start(request)["id"])
        assert first["status"] == "completed" and first["applied"]
        assert first["depth"] >= 8 and len(first["lines"]) == 3
        assert first["settings"]["threads"] == manager.engine.protocol.config["Threads"] == 1
        assert first["settings"]["hash_mb"] == manager.engine.protocol.config["Hash"] == 16
        assert first["memory_mb"] > 16
        for line in first["lines"]:
            board = chess.Board()
            for uci, san in zip(line["pv_uci"], line["pv_san"]):
                move = board.parse_uci(uci)
                assert board.san(move) == san
                board.push(move)
        request.sequence = 2
        request.settings = SearchSettings(mode="infinite", threads=1, hash_mb=16)
        forever = manager.start(request.model_copy(deep=True))["id"]
        time.sleep(0.2)
        request.sequence = 3
        request.moves = ["e2e4"]
        request.settings = SearchSettings(mode="time", seconds=0.25, threads=2, hash_mb=32, multipv=2)
        timed = wait_job(manager, manager.start(request.model_copy(deep=True))["id"])
        assert timed["status"] == "completed"
        assert 0.15 <= timed["elapsed"] < 2.0
        assert timed["settings"]["threads"] == manager.engine.protocol.config["Threads"] == 2
        assert timed["settings"]["hash_mb"] == manager.engine.protocol.config["Hash"] == 32
        assert wait_job(manager, forever)["status"] == "stopped"
        with pytest.raises(ValueError, match="替代"):
            manager.start(request)
        request.sequence = 4
        request.settings.mode = "infinite"
        stopping = manager.start(request)["id"]
        manager.stop(stopping)
        assert wait_job(manager, stopping)["status"] == "stopped"
    finally:
        manager.close()
    assert not manager.worker.is_alive()


def test_abandoned_infinite_search_expires(engine_path):
    manager = LiveAnalysis(engine_path, lease_seconds=0.3)
    try:
        request = StartSearch(client_id="test", sequence=1, root_fen=chess.STARTING_FEN,
                              settings=SearchSettings(mode="infinite", threads=1, hash_mb=16))
        job = manager.start(request)["id"]
        time.sleep(2)
        assert manager.read(job)["status"] == "stopped"
    finally:
        manager.close()


def test_terminal_position_does_not_spawn_engine(engine_path):
    manager = LiveAnalysis(engine_path)
    try:
        request = StartSearch(client_id="test", sequence=1, root_fen=chess.STARTING_FEN,
                              moves=["f2f3", "e7e5", "g2g4", "d8h4"])
        result = wait_job(manager, manager.start(request)["id"])
        assert result["outcome"] == {"result": "0-1", "reason": "checkmate"}
        assert result["lines"] == [] and manager.engine is None
    finally:
        manager.close()
