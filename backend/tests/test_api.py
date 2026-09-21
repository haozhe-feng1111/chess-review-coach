"""HTTP endpoint tests.

The service is injected through FastAPI's dependency override with an isolated database,
so the tests never touch the developer's real ``chess_coach.db``.
"""

import time

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from api.routes import service as service_dependency
from api.service import AnalysisService
from config import settings
from tests.conftest import requires_engine

SCHOLARS_MATE = """[Event "Test"]
[White "White"]
[Black "Black"]
[Result "0-1"]

1. e4 e5 2. Bc4 Nc6 3. Qh5 Nf6 4. Qxf7# 0-1
"""

INVALID_PGN = "this is not a chess game at all"


@pytest.fixture()
def api(temp_database, test_settings):
    application = create_app()
    analysis_service = AnalysisService(database=temp_database, settings=test_settings)
    application.dependency_overrides[service_dependency] = lambda: analysis_service
    client = TestClient(application)
    try:
        yield client, analysis_service
    finally:
        analysis_service.shutdown()
        application.dependency_overrides.clear()


def wait_for_job(client: TestClient, job_id: str, timeout: float = 120.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        payload = client.get("/api/jobs/{}".format(job_id)).json()["job"]
        if payload["status"] in ("completed", "failed"):
            return payload
        time.sleep(0.5)
    raise AssertionError("analysis job did not finish in time")


def test_root_and_config_endpoints(api):
    client, _service = api
    assert client.get("/").status_code == 200
    config = client.get("/api/config").json()
    assert config["max_critical_moments"] >= 3
    assert config["llm_configured"] is False


@requires_engine
def test_health_reports_engine_and_llm_availability(api):
    client, _service = api
    payload = client.get("/api/health").json()
    assert payload["status"] == "ok"
    assert payload["engine"]["available"] is True
    assert "Stockfish" in payload["engine"]["name"]
    assert payload["llm"]["available"] is False
    assert payload["pass1_depth"] > 0


def test_health_reports_a_missing_engine_without_crashing(temp_database, test_settings):
    application = create_app()
    broken_settings = test_settings.model_copy(
        update={"stockfish_path": "/nonexistent/stockfish"}
    )
    analysis_service = AnalysisService(database=temp_database, settings=broken_settings)
    application.dependency_overrides[service_dependency] = lambda: analysis_service
    client = TestClient(application)
    try:
        payload = client.get("/api/health").json()
        assert payload["status"] == "degraded"
        assert payload["engine"]["available"] is False
        assert payload["engine"]["error"]
    finally:
        analysis_service.shutdown()
        application.dependency_overrides.clear()


def test_invalid_pgn_returns_400_with_a_chinese_hint(api):
    client, _service = api
    response = client.post("/api/games/analyze", json={"pgn": INVALID_PGN})
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "PGN" in detail["error"] or "game" in detail["error"]
    assert detail["hint_zh"]


def test_empty_pgn_is_rejected_by_validation(api):
    client, _service = api
    assert client.post("/api/games/analyze", json={"pgn": ""}).status_code == 422


def test_unknown_game_and_job_return_404(api):
    client, _service = api
    assert client.get("/api/games/does-not-exist").status_code == 404
    assert client.get("/api/jobs/does-not-exist").status_code == 404
    assert client.get("/api/games/does-not-exist/moments/2/explanation").status_code == 404


@requires_engine
def test_full_analysis_flow(api):
    client, _service = api

    response = client.post(
        "/api/games/analyze",
        json={"pgn": SCHOLARS_MATE, "player_color": "black", "max_critical_moments": 3},
    )
    assert response.status_code == 200
    started = response.json()
    game_id = started["game_id"]
    assert started["status"]["status"] in ("pending", "running", "completed")

    job = wait_for_job(client, started["job_id"])
    assert job["status"] == "completed", job
    assert job["progress"] == pytest.approx(1.0)

    review = client.get("/api/games/{}".format(game_id)).json()["review"]
    assert review["player_color"] == "black"
    assert len(review["moves"]) == 7
    assert review["critical_moments"], "the Nf6 blunder must be reported"

    moment = review["critical_moments"][0]
    assert moment["move_number"] == 3
    assert moment["severity"] == "blunder"
    assert moment["one_liner_zh"]
    assert moment["solution_san"]
    assert moment["evidence"]["engine"]["mate_after"] == -1
    assert moment["evidence"]["concepts"]

    # Explanation endpoint: engine review must work with no LLM configured.
    explanation = client.get(
        "/api/games/{}/moments/{}/explanation".format(game_id, moment["ply"])
    ).json()["explanation"]
    assert explanation["source"] == "rules"
    assert explanation["explanation"]["general_lesson"]
    assert explanation["explanation"]["confidence"] > 0

    # A non-critical ply has no explanation.
    assert (
        client.get("/api/games/{}/moments/1/explanation".format(game_id)).status_code == 404
    )

    # 线路演示：引擎推荐线路 + 实战线路，都能逐步展开
    lines = client.get("/api/games/{}/moments/{}/lines".format(game_id, moment["ply"])).json()
    assert lines["ply"] == moment["ply"]
    assert lines["best"]["kind"] == "best"
    assert lines["played"]["kind"] == "played"
    assert lines["best"]["steps"], "引擎线路不能为空"
    assert lines["best"]["steps"][0]["san"] == lines["best_move_san"]
    assert lines["best"]["steps"][0]["uci"] == moment["solution_uci"]
    assert lines["played"]["steps"][0]["san"] == moment["played_move_san"]
    assert lines["best"]["start_fen"] == moment["fen"]
    assert lines["best"]["complete"] is True
    # 每一步都要带上走完之后的局面，前端才能直接播放
    for step in lines["best"]["steps"]:
        assert step["fen_after"] and step["mover"] in ("white", "black")
    # 关键局面里白方被将杀，实战线路必然以将杀收尾
    assert lines["played"]["ends_in_mate"] is True

    # 线路演示：任何一手都能查，不限于关键局面
    any_ply = review["moves"][0]["ply"]
    lines_any = client.get("/api/games/{}/moves/{}/lines".format(game_id, any_ply)).json()
    assert lines_any["best"]["steps"], "每一手都应该能展开引擎线路"
    assert lines_any["best"]["steps"][0]["san"] == review["moves"][0]["best_move_san"]
    assert lines_any["played"]["steps"][0]["san"] == review["moves"][0]["san"]
    # 旧路径仍然可用（前端早期版本用的是它）
    assert (
        client.get("/api/games/{}/moments/{}/lines".format(game_id, any_ply)).status_code == 200
    )

    summary = client.get("/api/games/{}/summary".format(game_id)).json()["summary"]
    assert summary["source"] == "rules"
    assert summary["explanation"]["summary"]

    games = client.get("/api/games").json()["games"]
    assert [game["game_id"] for game in games] == [game_id]
    assert games[0]["blunders"] >= 1

    profile = client.get("/api/profile").json()
    assert profile["total_games"] == 1
    assert profile["total_problems"] >= 1
    assert profile["weaknesses"]
    assert "样本" in profile["sample_size_note_zh"]
    assert profile["trend"]["available"] is False

    deleted = client.delete("/api/games/{}".format(game_id)).json()
    assert deleted["deleted"] is True
    assert client.get("/api/games/{}".format(game_id)).status_code == 404
    assert client.get("/api/profile").json()["total_games"] == 0


@requires_engine
def test_reanalysis_of_the_same_game_reuses_the_stored_review(api):
    client, _service = api
    body = {"pgn": SCHOLARS_MATE, "player_color": "black"}

    first = client.post("/api/games/analyze", json=body).json()
    wait_for_job(client, first["job_id"])

    second = client.post("/api/games/analyze", json=body).json()
    assert second["game_id"] == first["game_id"]
    assert second["status"]["status"] == "completed"
    assert "已经分析过" in second["status"]["message_zh"]

    forced = client.post("/api/games/analyze", json=dict(body, force=True)).json()
    assert forced["status"]["status"] in ("pending", "running")


def test_llm_test_endpoint_without_a_key_explains_what_to_do(api):
    client, _service = api
    payload = client.post("/api/llm/test").json()
    assert payload["configured"] is False
    assert payload["ok"] is False
    assert "DEEPSEEK_API_KEY" in payload["message_zh"]
    assert payload["detail"] == "missing_api_key"


def test_llm_test_endpoint_reports_a_broken_key_in_chinese(temp_database, test_settings):
    """配了 Key 但不可用时，要给出可执行的建议，而不是把英文错误甩给用户。

    这里刻意指向一个不存在的本地端口：既能验证错误处理，又不会真的打到线上。
    """
    application = create_app()
    broken = test_settings.model_copy(
        update={"deepseek_api_key": "sk-definitely-not-valid", "llm_timeout": 2.0}
    )
    analysis_service = AnalysisService(database=temp_database, settings=broken)
    application.dependency_overrides[service_dependency] = lambda: analysis_service
    client = TestClient(application)
    try:
        payload = client.post("/api/llm/test").json()
        assert payload["configured"] is True
        assert payload["ok"] is False
        assert payload["detail"]
        # 必须给出中文的下一步建议，而不是把英文错误原样抛回来
        message = payload["message_zh"]
        assert any("\u4e00" <= char <= "\u9fff" for char in message), message
        assert message != payload["detail"]
    finally:
        analysis_service.shutdown()
        application.dependency_overrides.clear()


def test_profile_of_an_empty_database_is_honest(api):
    client, _service = api
    profile = client.get("/api/profile").json()
    assert profile["total_games"] == 0
    assert profile["weaknesses"] == []
    assert "还没有分析过对局" in profile["sample_size_note_zh"]
