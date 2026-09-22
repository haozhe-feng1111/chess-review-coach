"""Persistence: schema integrity, round trips, profile inputs, caches."""

from datetime import datetime

import pytest
from sqlalchemy.orm import configure_mappers

import storage.models  # noqa: F401  (registers the mappers)
from models.enums import Color, DecisionErrorType, GamePhase, Severity
from models.review import (
    CriticalMoment,
    EngineMeta,
    GameReview,
    MoveAssessment,
    MoveCounts,
)
from storage.cache import SqliteAnalysisCache, SqliteExplanationCache
from storage.repository import (
    collect_profile_input,
    delete_game,
    get_review,
    known_player_names,
    list_games,
    make_game_id,
    save_review,
)


def test_all_mappers_configure():
    """Catches relationship typos (a wrong back_populates fails only at query time)."""
    import chess

    configure_mappers()


def build_review(game_id: str = "game-1", player_color: Color = Color.BLACK) -> GameReview:
    from tests.test_llm import build_evidence

    evidence = build_evidence()
    moment = CriticalMoment(
        ply=6,
        move_number=3,
        player_color=player_color,
        phase=GamePhase.OPENING,
        severity=Severity.BLUNDER,
        criticality_score=1.25,
        reasons=[],
        one_liner_zh="你漏掉了对手的杀棋。",
        fen=evidence.position.fen,
        played_move_san="Nf6",
        solution_uci="g7g6",
        solution_san="g6",
        evidence=evidence,
    )
    moves = [
        MoveAssessment(
            ply=1,
            move_number=1,
            color=Color.WHITE,
            san="e4",
            uci="e2e4",
            fen_before="start",
            fen_after="after-e4",
            is_player_move=False,
            severity=Severity.BEST,
            expected_score_loss=0.0,
            evaluation_after=0.3,
        ),
        MoveAssessment(
            ply=2,
            move_number=1,
            color=Color.BLACK,
            san="e5",
            uci="e7e5",
            fen_before="after-e4",
            fen_after="after-e5",
            is_player_move=True,
            severity=Severity.GOOD,
            expected_score_loss=0.03,
            evaluation_after=0.2,
        ),
        MoveAssessment(
            ply=6,
            move_number=3,
            color=Color.BLACK,
            san="Nf6",
            uci="g8f6",
            fen_before=evidence.position.fen,
            fen_after="after-nf6",
            is_player_move=True,
            severity=Severity.BLUNDER,
            expected_score_loss=0.775,
            evaluation_after=-10.0,
            concept_tags=[concept.type for concept in evidence.concepts],
            decision_error_tags=[],
            is_critical=True,
        ),
    ]
    return GameReview(
        game_id=game_id,
        white="Alpha",
        black="Beta",
        result="1-0",
        player_color=player_color,
        opening="意大利开局",
        headers={"White": "Alpha", "Black": "Beta"},
        moves=moves,
        critical_moments=[moment],
        counts=MoveCounts(best=1, good=1, blunder=1),
        average_expected_score_loss=0.4,
        engine=EngineMeta(engine_name="Stockfish 19", pass1_depth=12, positions_analyzed=7),
        created_at=datetime(2024, 1, 1, 12, 0, 0),
    )


def test_game_ids_are_deterministic_and_side_sensitive():
    pgn = "[White \"A\"]\n\n1. e4 e5 *"
    assert make_game_id(pgn, "white") == make_game_id(pgn + "\n\n", "white")
    assert make_game_id(pgn, "white") != make_game_id(pgn, "black")
    assert make_game_id(pgn, "white") != make_game_id(pgn.replace("e4", "d4"), "white")


def test_save_and_load_review_round_trip(temp_database):
    review = build_review()
    with temp_database.session() as session:
        save_review(session, review, "pgn-text")

    with temp_database.session() as session:
        restored = get_review(session, "game-1")

    assert restored is not None
    assert restored.white == "Alpha"
    assert restored.opening == "意大利开局"
    assert len(restored.critical_moments) == 1
    assert restored.critical_moments[0].evidence.engine.best_move_san == "g6"
    assert restored.counts.blunder == 1
    assert restored.engine.engine_name == "Stockfish 19"
    assert restored.created_at == datetime(2024, 1, 1, 12, 0, 0)


def test_saving_the_same_game_twice_replaces_it(temp_database):
    review = build_review()
    with temp_database.session() as session:
        save_review(session, review, "pgn")
    with temp_database.session() as session:
        save_review(session, review, "pgn")

    assert len(list_games_from(temp_database)) == 1
    with temp_database.session() as session:
        input_data = collect_profile_input(session)
    assert len(input_data.mistake_events) == 1, "mistake events must not be duplicated"


def list_games_from(database):
    with database.session() as session:
        return list_games(session)


def test_mistake_events_capture_the_analytics_payload(temp_database):
    with temp_database.session() as session:
        save_review(session, build_review(), "pgn")

    with temp_database.session() as session:
        data = collect_profile_input(session)

    assert data.total_games == 1
    assert data.total_player_moves == 2
    assert len(data.mistake_events) == 1
    event = data.mistake_events[0]
    assert event["severity"] == "blunder"
    assert event["phase"] == "opening"
    assert event["primary_error"] == DecisionErrorType.UNKNOWN.value
    assert event["expected_score_loss"] == pytest.approx(0.775)
    assert event["fen"].startswith("r1bqkb1r")
    assert event["solution_san"] == "g6"
    assert event["opponent"] == "Alpha"
    assert data.phase_counts and data.phase_counts[0]["events"] == 1


def test_concepts_are_stored_for_each_mistake(temp_database):
    with temp_database.session() as session:
        save_review(session, build_review(), "pgn")

    with temp_database.session() as session:
        data = collect_profile_input(session)

    assert data.concept_counts
    assert data.concept_counts[0]["concept"] == "mating_threat"


def test_player_move_rows_are_marked_for_average_loss(temp_database):
    with temp_database.session() as session:
        save_review(session, build_review(), "pgn")
    with temp_database.session() as session:
        data = collect_profile_input(session)
    # Only the player's own moves count towards the average.
    assert data.average_loss == pytest.approx((0.03 + 0.775) / 2, abs=0.001)


def test_game_listing_and_known_player_names(temp_database):
    with temp_database.session() as session:
        save_review(session, build_review(), "pgn")

    with temp_database.session() as session:
        games = list_games(session)
        names = known_player_names(session)

    assert len(games) == 1
    assert games[0].game_id == "game-1"
    assert games[0].blunders == 1
    assert "Alpha" in names and "Beta" in names


def test_delete_removes_the_game_and_its_events(temp_database):
    with temp_database.session() as session:
        save_review(session, build_review(), "pgn")

    with temp_database.session() as session:
        assert delete_game(session, "game-1") is True

    with temp_database.session() as session:
        assert get_review(session, "game-1") is None
        data = collect_profile_input(session)
    assert data.mistake_events == []
    assert data.total_games == 0


def test_engine_cache_round_trip(temp_database):
    from models.evidence import CandidateMove, PositionEval, WdlDistribution

    cache = SqliteAnalysisCache(temp_database)
    assert cache.get("missing") is None

    value = PositionEval(
        fen="start",
        pov_color=Color.WHITE,
        depth=12,
        multipv=2,
        engine_name="Stockfish 19",
        candidates=[
            CandidateMove(
                uci="e2e4",
                san="e4",
                cp=25,
                wdl=WdlDistribution(win=0.4, draw=0.5, loss=0.1),
                expected_score=0.65,
            )
        ],
    )
    cache.put("key-1", value)
    restored = cache.get("key-1")
    assert restored is not None
    assert restored.depth == 12
    assert restored.candidates[0].uci == "e2e4"
    assert restored.candidates[0].wdl.win == pytest.approx(0.4)
    assert cache.hits == 1


def test_explanation_cache_round_trip(temp_database):
    cache = SqliteExplanationCache(temp_database)
    assert cache.get("k") is None
    cache.put("moment:abc", {"source": "rules", "explanation": {"summary": "x"}})
    restored = cache.get("moment:abc")
    assert restored is not None
    assert restored["cached"] is True
    assert restored["explanation"]["summary"] == "x"

    cache.put("moment:abc", {"source": "llm", "explanation": {"summary": "y"}})
    assert cache.get("moment:abc")["explanation"]["summary"] == "y"


def test_profile_input_is_empty_for_a_fresh_database(temp_database):
    with temp_database.session() as session:
        data = collect_profile_input(session)
    assert data.total_games == 0
    assert data.mistake_events == []
    assert data.game_trend == []


def test_existing_database_gains_new_columns_without_data_loss(tmp_path):
    """旧版本建的库遇到新字段时要自动补列，而不是整块查询报 no such column。

    做法：先手工建一张"缺列"的 games 表（模拟上一个版本），塞一行数据，
    再让 Database.create_all() 跑一遍，确认列补上了、老数据还在。
    """
    from sqlalchemy import inspect, text

    from storage.db import Database

    url = "sqlite:///{}".format(tmp_path / "legacy.db")
    legacy = Database(url)
    with legacy.engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE games ("
                "id VARCHAR(64) PRIMARY KEY, created_at DATETIME NOT NULL, "
                "white VARCHAR(128), black VARCHAR(128), result VARCHAR(16), "
                "player_color VARCHAR(8), pgn TEXT, move_count INTEGER, "
                "player_move_count INTEGER, blunders INTEGER, mistakes INTEGER, "
                "inaccuracies INTEGER, critical_count INTEGER, average_loss FLOAT, "
                "engine_name VARCHAR(64), analysis_seconds FLOAT, status VARCHAR(16)"
                ")"
            )
        )
        connection.execute(
            text("INSERT INTO games (id, created_at, white, black) VALUES ('g1', '2024-01-01', 'me', 'op')")
        )

    legacy.create_all()  # create_all + ensure_columns

    columns = {column["name"] for column in inspect(legacy.engine).get_columns("games")}
    assert "review_json" in columns  # 新列补上了
    assert "puzzles" in set(inspect(legacy.engine).get_table_names())  # 新表也建了
    with legacy.engine.begin() as connection:
        row = connection.execute(text("SELECT white, black FROM games WHERE id = 'g1'")).one()
    assert tuple(row) == ("me", "op")  # 老数据没被动过
    legacy.dispose()


def test_ensure_columns_is_idempotent(temp_database):
    """第二次启动不能再加一遍列，也不能报错。"""
    from storage.db import ensure_columns

    assert ensure_columns(temp_database.engine) == []


def test_primary_error_covers_every_problem_move_not_just_critical_ones(temp_database):
    """回归测试：档案里的"主要失误原因"必须覆盖**每一个**问题着法。

    这条曾经是真 bug：primary_error 只从关键局面的证据里取，而一盘棋最多几个关键局面，
    于是其余失误全被记成"原因不明确"——档案里最大的那一类反而成了"说不清"。
    """
    from analysis.profile import build_profile
    from models.enums import DecisionErrorType
    from models.review import MoveAssessment
    from storage.models import MistakeEvent
    from storage.repository import collect_profile_input

    review = build_review()
    # 这一手不是关键局面（critical_moments 里只有 ply=6），但确实有问题、也有原因
    extra = MoveAssessment(
        ply=20,
        move_number=10,
        color=Color.BLACK,
        san="Nd4",
        uci="f6d4",
        fen_before="before-20",
        fen_after="after-20",
        is_player_move=True,
        severity=Severity.BLUNDER,
        expected_score_loss=0.55,
        evaluation_after=-3.0,
        decision_error_tags=[DecisionErrorType.HANGING_PIECE],
        primary_error=DecisionErrorType.HANGING_PIECE,
        primary_error_confidence=0.9,
        is_critical=False,
    )
    review.moves.append(extra)
    review.created_at = datetime(2024, 1, 2, 12, 0, 0)

    with temp_database.session() as session:
        save_review(session, review, "1. e4 e5 *")

    with temp_database.session() as session:
        events = {
            event.ply: event for event in session.query(MistakeEvent).all()
        }
        data = collect_profile_input(session)
    assert events[20].primary_error == DecisionErrorType.HANGING_PIECE.value
    assert events[20].primary_error_confidence == 0.9

    profile = build_profile(data)
    unknown = next(
        (item for item in profile.weaknesses if item.error_type is DecisionErrorType.UNKNOWN),
        None,
    )
    # 只剩 fixture 里那个本来就没有任何标签的关键局面算"原因不明确"；
    # 新增的那一手（非关键局面、但有明确原因）必须落进它自己的类别里。
    assert unknown is None or unknown.event_count == 1
    hanging = next(
        item for item in profile.weaknesses if item.error_type is DecisionErrorType.HANGING_PIECE
    )
    assert hanging.event_count >= 1
    assert hanging.games == 1
