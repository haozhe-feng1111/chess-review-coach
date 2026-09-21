"""End-to-end pipeline test: PGN -> engine -> critical positions -> evidence concepts.

Uses the real engine with a deliberately small budget so the suite stays fast. This is
the test that proves the whole chain produces *valid structured data* rather than the
individual pieces working in isolation.
"""

from pathlib import Path

import pytest

from analysis.pgn import parse_pgn
from analysis.pipeline import GameAnalyzer, PipelineConfig
from engine.cache import InMemoryCache
from models.enums import Color, Severity
from tests.conftest import requires_engine

SCHOLARS_MATE = """[Event "Test"]
[White "White"]
[Black "Black"]
[Result "0-1"]

1. e4 e5 2. Bc4 Nc6 3. Qh5 Nf6 4. Qxf7# 0-1
"""

LEGAL_GAME = """[Event "Test"]
[White "Alpha"]
[Black "Beta"]
[Result "1-0"]

1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 4. Ba4 Nf6 5. O-O Be7 6. Re1 b5 7. Bb3 d6 1-0
"""

FAST_CONFIG = PipelineConfig(
    pass1_depth=8,
    pass2_depth=10,
    pass2_multipv=3,
    max_critical_moments=3,
    deep=True,
    threads=2,
    hash_mb=32,
    position_timeout=30.0,
)


@requires_engine
def test_pipeline_flags_the_scholars_mate_blunder(engine):
    game = parse_pgn(SCHOLARS_MATE, player_color=Color.BLACK)
    analyzer = GameAnalyzer(engine, cache=InMemoryCache(), config=FAST_CONFIG)
    review = analyzer.analyze(game, "test-scholars")

    assert len(review.moves) == 7
    assert review.player_color is Color.BLACK

    # Black's 3...Nf6 allows mate in one and must be the critical moment.
    assert review.critical_moments, "expected at least one critical moment"
    moment = review.critical_moments[0]
    assert moment.move_number == 3
    assert moment.played_move_san == "Nf6"
    assert moment.severity is Severity.BLUNDER

    evidence = moment.evidence
    assert evidence.engine.mate_after == -1
    assert evidence.engine.expected_score_loss > 0.4
    assert evidence.engine.best_move_san
    assert evidence.engine.played_line_san[0] == "Nf6"

    # The evidence object must be complete and self-consistent.
    assert evidence.position.player_color is Color.BLACK
    assert evidence.engine.wdl_after.win == pytest.approx(0.0, abs=0.01)
    assert evidence.decision_errors, "a blunder that allows mate must be classified"
    concept_values = {concept.type.value for concept in evidence.concepts}
    assert "mating_threat" in concept_values

    # Future-trainer hooks: the position can be re-asked as a puzzle.
    assert moment.fen
    assert moment.solution_uci
    assert moment.solution_san


@requires_engine
def test_pipeline_labels_every_move_and_counts_severities(engine):
    game = parse_pgn(SCHOLARS_MATE, player_color=Color.BLACK)
    review = GameAnalyzer(engine, cache=InMemoryCache(), config=FAST_CONFIG).analyze(
        game, "test-counts"
    )

    assert all(move.severity is not None for move in review.moves)
    counts = review.counts
    assert counts.blunder + counts.mistake + counts.inaccuracy >= 1
    assert counts.best + counts.excellent + counts.good + counts.problems == len(
        [m for m in review.moves if m.is_player_move]
    )
    # The final move is White's mate: terminal position handled without an engine PV.
    last = review.moves[-1]
    assert last.san == "Qxf7#"
    assert last.evaluation_after is not None


@requires_engine
def test_quiet_game_produces_no_invented_critical_moments(engine):
    game = parse_pgn(LEGAL_GAME, player_color=Color.WHITE)
    review = GameAnalyzer(engine, cache=InMemoryCache(), config=FAST_CONFIG).analyze(
        game, "test-quiet"
    )

    # An opening with no blunders must not be padded with "critical positions".
    assert len(review.critical_moments) <= 2
    for moment in review.critical_moments:
        assert moment.severity.is_problem
        assert moment.evidence.engine.expected_score_loss > 0.0
    # A move the engine rates as good carries no concept tags at all: concepts exist to
    # explain problems, and tagging a best move with "material loss" would mislead.
    for move in review.moves:
        if move.severity in (Severity.BEST, Severity.EXCELLENT, Severity.GOOD):
            assert move.concept_tags == [], "concepts on a good move: {}".format(
                move.concept_tags
            )
            assert move.decision_error_tags == []


@requires_engine
def test_every_move_carries_a_legal_engine_recommendation(engine):
    """每一手都要有引擎推荐，而且这个推荐必须在"走子之前"的局面里合法。

    这正是复盘页上出过的那类错误：把"走子前"的推荐画到"走子后"的局面上，
    箭头指向一个根本走不了的着法。
    """
    import chess

    game = parse_pgn(LEGAL_GAME, player_color=Color.WHITE)
    review = GameAnalyzer(engine, cache=InMemoryCache(), config=FAST_CONFIG).analyze(
        game, "test-best-moves"
    )

    assert review.moves
    for move in review.moves:
        assert move.best_move_san, "第 {} 手缺少引擎推荐".format(move.ply)
        assert move.best_move_uci, "第 {} 手缺少引擎推荐（uci）".format(move.ply)

        board = chess.Board(move.fen_before)
        legal = {candidate.uci() for candidate in board.legal_moves}
        assert move.best_move_uci in legal, (
            "第 {} 手的引擎推荐 {} 在走子前的局面里不合法".format(move.ply, move.best_move_uci)
        )

        # 顺带确认：实战走法在同一个局面里当然也是合法的
        assert move.uci in legal


@requires_engine
def test_best_move_is_marked_when_the_player_followed_it(engine):
    game = parse_pgn(LEGAL_GAME, player_color=Color.WHITE)
    review = GameAnalyzer(engine, cache=InMemoryCache(), config=FAST_CONFIG).analyze(
        game, "test-engine-best-flag"
    )
    followed = [m for m in review.moves if m.is_engine_best]
    assert followed, "正常开局里总该有几手就是引擎首选"
    for move in followed:
        assert move.best_move_san == move.san


@requires_engine
def test_every_move_carries_a_walkable_line(engine):
    """每一手都要带后续线路，而且从该局面能一步步走完（复盘页的线路演示靠这个）。"""
    import chess

    game = parse_pgn(LEGAL_GAME, player_color=Color.WHITE)
    review = GameAnalyzer(engine, cache=InMemoryCache(), config=FAST_CONFIG).analyze(
        game, "test-lines"
    )

    for move in review.moves:
        assert move.best_line_uci, "第 {} 手缺少引擎线路".format(move.ply)
        assert move.best_line_uci[0] == move.best_move_uci
        assert len(move.best_line_san) == len(move.best_line_uci)
        assert move.played_line_uci and move.played_line_uci[0] == move.uci
        assert len(move.played_line_san) == len(move.played_line_uci)

        # 两条线路都必须能从「走子之前」的局面一步步走完
        for line in (move.best_line_uci, move.played_line_uci):
            board = chess.Board(move.fen_before)
            for uci in line:
                candidate = chess.Move.from_uci(uci)
                assert candidate in board.legal_moves, (
                    "第 {} 手的线路里有不合法的着法 {}".format(move.ply, uci)
                )
                board.push(candidate)


@requires_engine
def test_second_run_is_served_from_the_cache(engine):
    cache = InMemoryCache()
    game = parse_pgn(LEGAL_GAME, player_color=Color.WHITE)
    first = GameAnalyzer(engine, cache=cache, config=FAST_CONFIG).analyze(game, "cache-a")
    second = GameAnalyzer(engine, cache=cache, config=FAST_CONFIG).analyze(game, "cache-b")

    assert first.engine.cache_hits == 0
    assert second.engine.cache_hits > 0
    assert second.engine.positions_analyzed <= first.engine.positions_analyzed


@requires_engine
def test_analysis_without_deep_pass_still_produces_a_review(engine):
    game = parse_pgn(SCHOLARS_MATE, player_color=Color.BLACK)
    config = PipelineConfig(pass1_depth=8, deep=False, threads=2, hash_mb=32)
    review = GameAnalyzer(engine, cache=InMemoryCache(), config=config).analyze(
        game, "test-shallow"
    )
    assert review.engine.pass2_depth == 0
    assert review.critical_moments
    # No MultiPV alternatives were computed, so uniqueness stays False rather than guessed.
    assert all(
        moment.evidence.engine.alternatives == []
        for moment in review.critical_moments
    )


@requires_engine
def test_phase_classification_is_recorded_for_every_move(engine):
    from models.enums import GamePhase

    game = parse_pgn(LEGAL_GAME, player_color=Color.WHITE)
    review = GameAnalyzer(engine, cache=InMemoryCache(), config=FAST_CONFIG).analyze(
        game, "test-phase"
    )
    phases = {stat.phase for stat in review.phase_stats}
    assert GamePhase.OPENING in phases
    assert all(stat.moves >= 0 for stat in review.phase_stats)


@requires_engine
def test_review_serializes_and_deserializes_unchanged(engine):
    from models.review import GameReview

    game = parse_pgn(LEGAL_GAME, player_color=Color.WHITE)
    review = GameAnalyzer(engine, cache=InMemoryCache(), config=FAST_CONFIG).analyze(
        game, "test-serialization"
    )
    payload = review.model_dump(mode="json")
    restored = GameReview.model_validate(payload)
    assert restored.model_dump(mode="json") == payload
