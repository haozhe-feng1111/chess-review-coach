"""End-to-end pipeline test: PGN -> engine -> critical positions -> evidence concepts.

Uses the real engine with a deliberately small budget so the suite stays fast. This is
the test that proves the whole chain produces *valid structured data* rather than the
individual pieces working in isolation.
"""

from pathlib import Path

import re

import pytest

from analysis.pgn import parse_pgn
from analysis.pipeline import GameAnalyzer, PipelineConfig
from engine.cache import InMemoryCache
from models.enums import Color, Severity
from models.evidence import CandidateMove, PositionEval, WdlDistribution
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


# ------------------------------------------------- 逐手时钟 → 时间压力（真实引擎）

#: 白方在只剩 11 秒时走了 5.Bxf7+，被 Kxf7 白吃一象——时间压力下的典型崩盘
CLOCKED_BLUNDER = """[Event "Live Chess"]
[Site "Chess.com"]
[White "Alpha"]
[Black "Beta"]
[Result "0-1"]
[TimeControl "180"]

1. e4 {[%clk 0:02:55]} e5 {[%clk 0:02:56]} 2. Nf3 {[%clk 0:02:40]} Nc6 {[%clk 0:02:41]}
3. Bc4 {[%clk 0:02:20]} Bc5 {[%clk 0:02:21]} 4. Qe2 {[%clk 0:00:45]} Nf6 {[%clk 0:00:50]}
5. Bxf7+ {[%clk 0:00:11]} Kxf7 {[%clk 0:00:14]} 6. Qc4+ {[%clk 0:00:09]} d5 0-1
"""


def strip_clocks(pgn: str) -> str:
    return re.sub(r"\s*\{\[%clk[^}]*\]\}", "", pgn)


@requires_engine
def test_time_pressure_attribution_on_a_clocked_game(engine):
    """有逐手时钟时：能不能说出"这一步是在剩 11 秒时走的"。"""
    game = parse_pgn(CLOCKED_BLUNDER, player_color=Color.WHITE)
    assert game.has_clocks is True
    analyzer = GameAnalyzer(
        engine,
        cache=InMemoryCache(),
        config=PipelineConfig(pass1_depth=10, pass2_depth=12, deep=True, threads=2, hash_mb=32),
    )
    review = analyzer.analyze(game, "clocked")

    assert review.has_clocks is True
    assert review.time_control is not None and review.time_control.base_seconds == 180
    summary = review.time_pressure
    assert summary.available is True
    assert summary.limit_seconds == 20.0           # 3 分钟棋：10% = 18 秒 < 20 秒下限
    assert summary.problem_moves >= 1
    assert summary.under_pressure >= 1
    assert summary.moments[0].clock_seconds == 11.0
    assert "剩 11 秒" in summary.statement_zh

    blunder = next(move for move in review.moves if move.san == "Bxf7+")
    assert blunder.clock_seconds == 11.0
    assert blunder.time_pressure is True
    assert blunder.severity is not None and blunder.severity.is_problem


@requires_engine
def test_without_clocks_the_review_says_so_instead_of_guessing(engine):
    """没有时钟信息时：time_pressure 保持 None，并给出中文说明，而不是猜一个结论。"""
    game = parse_pgn(strip_clocks(CLOCKED_BLUNDER), player_color=Color.WHITE)
    assert game.has_clocks is False
    assert all(move.clock_seconds is None for move in game.moves)

    review = GameAnalyzer(
        engine,
        cache=InMemoryCache(),
        config=PipelineConfig(pass1_depth=10, pass2_depth=12, deep=True, threads=2, hash_mb=32),
    ).analyze(game, "unclocked")

    assert review.has_clocks is False
    assert review.time_pressure.available is False
    assert "没有每步剩余时间" in review.time_pressure.statement_zh
    assert all(move.time_pressure is None for move in review.moves)


def make_eval(fen, uci, san, cp, win=0.9, draw=0.09, loss=0.01) -> PositionEval:
    """造一个假的引擎结果，用来确定性地复现"两遍分析改判"的场景。"""
    return PositionEval(
        fen=fen,
        pov_color=Color.WHITE,
        depth=12,
        multipv=1,
        engine_name="fake",
        candidates=[
            CandidateMove(
                uci=uci,
                san=san,
                cp=cp,
                wdl=WdlDistribution(win=win, draw=draw, loss=loss),
                expected_score=round(win + 0.5 * draw, 4),
            )
        ],
    )


def test_second_pass_clears_tags_when_a_problem_becomes_a_good_move():
    """回归测试：浅搜判成"有问题"的着法，被深搜改判为"走对了"之后不能留着旧标签。

    这条曾经是真 bug：第二遍不重新跑概念检测，但因为"走对了就不打标签"而直接 continue，
    于是第一遍留下的 concept_tags 会残留在一条已经没问题的着法上，
    界面上就出现"最佳着法 + 丢子"这种自相矛盾的标注。
    真引擎下它表现为偶发失败（两次搜索的哈希状态不同会改变改判结果），所以这里用假评估确定性地复现。
    """
    game = parse_pgn(LEGAL_GAME, player_color=Color.WHITE)
    analyzer = GameAnalyzer(None, cache=InMemoryCache(), config=FAST_CONFIG)
    positions, slots = analyzer._build_slots(game)
    target = slots[0]                      # 白方第一手 e4
    played_uci = target.move.uci
    board_before = positions[target.before].board
    board_after = positions[target.after].board

    # 第一遍：白方"走错了"——引擎推荐另一步，期望得分差很多
    positions[target.before].shallow = make_eval(
        board_before.fen(), "d2d4", "d4", cp=30, win=0.55, draw=0.4, loss=0.05
    )
    positions[target.after].shallow = make_eval(
        board_after.fen(), "d7d5", "d5", cp=-420, win=0.05, draw=0.15, loss=0.8
    )
    analyzer._assemble_and_classify(positions, slots, deep=False)
    assert target.severity is not None and target.severity.is_problem
    assert target.concepts, "第一遍应该给问题着法打上概念标签"

    # 第二遍：深搜改判——这一步就是引擎最佳着法
    positions[target.before].deep = make_eval(
        board_before.fen(), played_uci, target.move.san, cp=25, win=0.5, draw=0.45, loss=0.05
    )
    positions[target.after].deep = make_eval(
        board_after.fen(), "d7d5", "d5", cp=20, win=0.48, draw=0.46, loss=0.06
    )
    analyzer._assemble_and_classify(positions, slots, deep=True)

    assert target.severity is not None and not target.severity.is_problem
    assert target.concepts == [], "改判为走对了之后，旧的概念标签必须清掉"
    assert target.errors == []
    assessment = analyzer._to_assessment(target, positions)
    assert assessment.concept_tags == []
    assert assessment.decision_error_tags == []
