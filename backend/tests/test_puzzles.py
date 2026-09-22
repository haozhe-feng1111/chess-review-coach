"""题目提取的测试。

出题规则必须是确定性的、可核实的，所以这里既测正例也测反例：
漏掉将杀 / 漏掉赚子要出题；自己走对了、走的是没有强制手段的着法、本来就劣势、
对手的漏着——都不该出题。
"""

import chess
import pytest

from analysis.puzzles import (
    extract_puzzles,
    material_swing,
    puzzle_id,
)
from models.enums import Color, ConceptType, GamePhase, PuzzleKind, Severity
from models.review import EngineMeta, GameReview, MoveAssessment
from tests.conftest import requires_engine

START = chess.STARTING_FEN
# 白方车 d1、黑方马 d5（无保护）：Rxd5 净赚一个轻子
FREE_KNIGHT = "4k3/8/8/3n4/8/8/8/3RK3 w - - 0 1"
# 白方少一车（-2.00），但 Nc7+ 叉住 e8 王与 a8 车：走对了净赚一车（+5.98），
# 走闲棋（Kh1）就变成 -6.79。这是一个真正“一步定胜负”的强制手段。
FORK_POSITION = "r3k3/1p3ppp/8/1N6/8/8/PP3PPP/6K1 w - - 0 1"


def make_move(**overrides) -> MoveAssessment:
    data = {
        "ply": 1,
        "move_number": 1,
        "color": Color.WHITE,
        "san": "h3",
        "uci": "h2h3",
        "fen_before": FREE_KNIGHT,
        "fen_after": "after",
        "is_player_move": True,
        "severity": Severity.MISTAKE,
        "expected_score_loss": 0.3,
        "evaluation_after": 0.0,
        "mate_after": None,
        "mate_before": None,
        "best_move_san": "Rxd5",
        "best_move_uci": "d1d5",
        "is_engine_best": False,
        "evaluation_before": 3.0,
        "expected_score_before": 0.95,
        "best_line_uci": ["d1d5"],
        "best_line_san": ["Rxd5"],
        "played_line_uci": ["h2h3"],
        "played_line_san": ["h3"],
        "concept_tags": [ConceptType.HANGING_PIECE],
        "decision_error_tags": [],
        "is_critical": True,
    }
    data.update(overrides)
    return MoveAssessment(**data)


def make_review(moves, game_id: str = "g1") -> GameReview:
    return GameReview(
        game_id=game_id,
        white="me",
        black="opponent",
        result="1-0",
        player_color=Color.WHITE,
        moves=moves,
        engine=EngineMeta(engine_name="Stockfish 19"),
    )


# ------------------------------------------------------------------ 子力变化


def test_material_swing_counts_a_won_piece():
    swing = material_swing(FREE_KNIGHT, ["d1d5"], player_is_white=True)
    assert swing.gain == 3
    assert swing.first_gain_ply == 1


def test_material_swing_is_zero_for_a_quiet_line():
    swing = material_swing(FREE_KNIGHT, ["d1d2"], player_is_white=True)
    assert swing.gain == 0
    assert swing.first_gain_ply is None


def test_material_swing_stops_at_an_illegal_move():
    # 线路里出现走不动的着法时，只按能走的部分计算，不能因此抛异常
    swing = material_swing(FREE_KNIGHT, ["d1d5", "e8e1"], player_is_white=True)
    assert swing.gain == 3


def test_material_swing_is_relative_to_the_player():
    # 同一盘棋，换成黑方视角看，黑方是亏的
    after = chess.Board(FREE_KNIGHT)
    after.push_san("Rxd5")
    swing = material_swing(after.fen(), ["e8d8"], player_is_white=False)
    assert swing.gain == 0


def test_first_gain_ply_is_the_first_gain_not_the_latest_one():
    """第 3 步白吃一车、后面又磨了几步时，"兑现步数"要记 3 而不是最后一步。

    这条是回归测试：早先的实现把 first_gain_ply 写成了"最大收益出现的步数"，
    结果 Nc7+ Nxa8（第 3 步白吃一车）被判成需要 10 步才兑现，题目反而被丢掉了。
    """
    line = [
        "b5c7", "e8d7", "c7a8", "d7c6", "a2a4",
        "b7b6", "b2b4", "c6b7", "a8b6", "b7b6",
    ]
    swing = material_swing(FORK_POSITION, line, player_is_white=True)
    assert swing.first_gain_ply == 3  # Nxa8 就在第 3 步
    # 第 9 步骑士吃 b6 兵时账面上到过 +6，但紧接着被 b7 兵吃回来，所以不算数
    assert swing.gain == 5

    # 只有零星进账、始终凑不满一个轻子的线路不算"赚到子"
    slow = material_swing(FORK_POSITION, ["a2a4", "b7b6", "b2b4"], player_is_white=True)
    assert (slow.gain, slow.first_gain_ply) == (0, None)


def test_transient_material_swing_is_not_a_gain():
    """账面上一度多 4 分、但对手下一手就吃回来的，不算赚到子力。

    局面取自一盘真实对局：白方 Bb7 之后黑方 Rxc7，白方 Bxc7 时账面 +4，
    可黑后马上把象吃回来，实际只赚一个兵。如果按"线路上的最大差值"算，
    这道题就会被标成"赚 4 分"——那是假的。
    """
    fen = "2r2rk1/2PRppbp/1q2n1p1/8/pp2B3/5QB1/PPP2PP1/2K4R w - - 0 22"
    line = ["e4b7", "c8c7", "g3c7", "b6c7"]
    swing = material_swing(fen, line, player_is_white=True)
    assert swing.gain == 1
    assert swing.first_gain_ply == 4


# --------------------------------------------------------------------- 出题


def test_missed_forced_mate_becomes_a_mate_puzzle():
    review = make_review([make_move(mate_before=3, mate_after=None)])
    puzzles = extract_puzzles(review)
    assert len(puzzles) == 1
    puzzle = puzzles[0]
    assert puzzle.kind is PuzzleKind.MATE
    assert puzzle.mate_in == 3
    assert puzzle.solution_san == "Rxd5"
    assert puzzle.fen == FREE_KNIGHT
    assert puzzle.played_san == "h3"
    assert puzzle.difficulty == "medium"
    assert puzzle.id == puzzle_id("g1", 1)


def test_short_mate_is_an_easy_puzzle_and_long_mate_is_hard():
    assert extract_puzzles(make_review([make_move(mate_before=1)]))[0].difficulty == "easy"
    assert extract_puzzles(make_review([make_move(mate_before=6)]))[0].difficulty == "hard"


def test_mate_that_is_still_available_afterwards_is_not_a_puzzle():
    # 玩家换了另一种杀法但仍然是强制将杀 → 他已经找到了，不用再练
    puzzles = extract_puzzles(make_review([make_move(mate_before=1, mate_after=2)]))
    assert puzzles == []


def test_playing_the_engine_move_is_not_a_puzzle():
    puzzles = extract_puzzles(make_review([make_move(is_engine_best=True, mate_before=1)]))
    assert puzzles == []


def test_missing_a_material_win_becomes_a_material_puzzle():
    puzzles = extract_puzzles(make_review([make_move()]))
    assert len(puzzles) == 1
    puzzle = puzzles[0]
    assert puzzle.kind is PuzzleKind.MATERIAL
    assert puzzle.material_gain == 3
    assert puzzle.theme is ConceptType.HANGING_PIECE
    assert puzzle.theme_label_zh == "悬子（无保护）"


def test_quiet_mistake_without_forcing_line_is_not_a_puzzle():
    puzzles = extract_puzzles(
        make_review(
            [
                make_move(
                    best_line_uci=["g1f3"],
                    best_line_san=["Nf3"],
                    expected_score_before=0.55,
                )
            ]
        )
    )
    assert puzzles == []


# 白方 Ne4 走到 f6 是安静的一步，但同时叉住 d7 车与 d5 后（不将军、不吃子）
QUIET_FORK = "7k/pp1r1pp1/8/3q4/4N3/8/PP3PPP/6K1 w - - 0 1"
# 同样的兵型，但没有任何可攻击的目标
NO_TARGETS = "4k3/8/8/8/8/8/8/3RK3 w - - 0 1"


def test_is_forcing_first_move_accepts_checks_captures_and_threats():
    from analysis.puzzles import is_forcing_first_move

    assert is_forcing_first_move(FREE_KNIGHT, "d1d5") is True   # 吃子
    assert is_forcing_first_move(FORK_POSITION, "b5c7") is True  # 将军
    assert is_forcing_first_move(QUIET_FORK, "e4f6") is True     # 安静的一步，但立刻叉住车和后


def test_is_forcing_first_move_rejects_idle_moves():
    from analysis.puzzles import is_forcing_first_move

    assert is_forcing_first_move(QUIET_FORK, "g1h1") is False
    assert is_forcing_first_move(NO_TARGETS, "d1d2") is False
    # 局面里根本没有这一手时也不能崩
    assert is_forcing_first_move(FREE_KNIGHT, "a1a8") is False


def test_quiet_first_move_is_not_a_puzzle_even_if_the_line_wins_material():
    """第一步只是"挪一下"、靠后面才赚到子力的局面不出题。

    这里刻意构造了一条能在第 5 步赚到一车的线路：如果只看"线路赚了多少"，
    它会被当成题目；但第一步 Kh1 不带任何具体威胁，换一步走也未必更差，
    做成题目就是在骗人。
    """
    puzzles = extract_puzzles(
        make_review(
            [
                make_move(
                    fen_before=QUIET_FORK,
                    best_move_uci="g1h1",
                    best_move_san="Kh1",
                    best_line_uci=["g1h1", "d5c5", "e4f6", "c5d5", "f6d7"],
                    best_line_san=["Kh1", "Qc5", "Nf6", "Qd5", "Nxd7"],
                    expected_score_before=0.9,
                )
            ]
        )
    )
    assert puzzles == []


def test_quiet_fork_that_threatens_material_is_a_puzzle():
    """对照组：同样是安静的第一步，但它立刻叉住车和后，就该出题。"""
    puzzles = extract_puzzles(
        make_review(
            [
                make_move(
                    fen_before=QUIET_FORK,
                    best_move_uci="e4f6",
                    best_move_san="Nf6",
                    best_line_uci=["e4f6", "d5c5", "f6d7"],
                    best_line_san=["Nf6", "Qc5", "Nxd7"],
                    expected_score_before=0.9,
                )
            ]
        )
    )
    assert len(puzzles) == 1
    puzzle = puzzles[0]
    assert puzzle.kind is PuzzleKind.MATERIAL
    # 线路在第 3 步兑现，就截到第 3 步为止
    assert puzzle.solution_line_uci == ["e4f6", "d5c5", "f6d7"]


def test_material_gain_too_late_in_the_line_is_not_a_puzzle():
    # 战术要在前几步兑现（上限 6 步），否则可能只是漫长的兑换
    puzzles = extract_puzzles(
        make_review(
            [
                make_move(
                    best_line_uci=[
                        "d1d2", "e8d8", "d2d1", "d8e8", "d1d2", "e8d8",
                        "d2d3", "d8e8", "d3d4", "e8d8", "d4d5",
                    ],
                    best_line_san=[
                        "Rd2", "Kd8", "Rd1", "Ke8", "Rd2", "Kd8",
                        "Rd3", "Ke8", "Rd4", "Kd8", "Rxd5",
                    ],
                )
            ]
        )
    )
    assert puzzles == []


def test_three_move_combination_still_counts_as_a_puzzle():
    """第 5 步才兑现的两步半组合仍然出题：线路会截到兑现的那一手。"""
    puzzles = extract_puzzles(
        make_review(
            [
                make_move(
                    best_line_uci=["d1d2", "e8d8", "d2d3", "d8e8", "d3d5", "e8d8"],
                    best_line_san=["Rd2", "Kd8", "Rd3", "Ke8", "Rxd5", "Kd8"],
                )
            ]
        )
    )
    assert len(puzzles) == 1
    assert puzzles[0].material_gain == 3
    assert puzzles[0].solution_line_uci == ["d1d2", "e8d8", "d2d3", "d8e8", "d3d5"]


def test_losing_position_is_not_a_puzzle_even_with_material_gain():
    puzzles = extract_puzzles(make_review([make_move(expected_score_before=0.4)]))
    assert puzzles == []


def test_opponent_moves_never_become_puzzles():
    puzzles = extract_puzzles(make_review([make_move(is_player_move=False, mate_before=1)]))
    assert puzzles == []


def test_theme_priority_prefers_the_most_characteristic_concept():
    puzzles = extract_puzzles(
        make_review(
            [
                make_move(
                    concept_tags=[ConceptType.PAWN_STRUCTURE_DAMAGE, ConceptType.FORK],
                )
            ]
        )
    )
    assert puzzles[0].theme is ConceptType.FORK


def test_puzzle_id_is_stable_across_reanalysis():
    assert puzzle_id("abc", 37) == puzzle_id("abc", 37)
    assert puzzle_id("abc", 37) != puzzle_id("abc", 38)
    assert puzzle_id("abc", 37) != puzzle_id("abd", 37)


def test_puzzles_carry_phase_from_the_critical_moment():
    review = make_review([make_move()])
    from models.review import CriticalMoment

    review.critical_moments = [
        CriticalMoment(
            ply=1,
            move_number=1,
            player_color=Color.WHITE,
            phase=GamePhase.ENDGAME,
            severity=Severity.MISTAKE,
            criticality_score=0.5,
            reasons=[],
            one_liner_zh="",
            fen=FREE_KNIGHT,
            played_move_san="h3",
            evidence=_evidence_for_phase_test(),
        )
    ]
    assert extract_puzzles(review)[0].phase is GamePhase.ENDGAME


def _evidence_for_phase_test():
    from tests.test_llm import build_evidence

    return build_evidence()


# --------------------------------------------------------------- 真实引擎


@requires_engine
def test_real_game_produces_a_material_puzzle(engine):
    """真实引擎跑一遍：漏掉叉子的局面应该被收成一道赚子题。"""
    from analysis.pgn import parse_pgn
    from analysis.pipeline import GameAnalyzer, PipelineConfig
    from engine.cache import InMemoryCache

    pgn = (
        '[Event "Puzzle Test"]\n[White "me"]\n[Black "opponent"]\n[Result "*"]\n'
        '[SetUp "1"]\n[FEN "{}"]\n\n1. Kh1 Kd7 *\n'.format(FORK_POSITION)
    )
    game = parse_pgn(pgn, player_color=Color.WHITE)
    review = GameAnalyzer(
        engine,
        cache=InMemoryCache(),
        config=PipelineConfig(pass1_depth=12, pass2_depth=14, deep=True, threads=2, hash_mb=32),
    ).analyze(game, "puzzle-test")

    puzzles = extract_puzzles(review)
    assert puzzles, "漏掉 Nc7+ 叉子应该出一道赚子题"
    puzzle = puzzles[0]
    assert puzzle.kind is PuzzleKind.MATERIAL
    assert puzzle.material_gain >= 3
    assert puzzle.solution_uci == "b5c7", puzzle.solution_uci
    assert puzzle.solution_uci
    # 题目局面就是玩家当时面对的局面，答案在题目局面里必须合法
    board = chess.Board(puzzle.fen)
    assert chess.Move.from_uci(puzzle.solution_uci) in board.legal_moves


def test_claimed_gain_equals_the_end_of_the_solution_line():
    """不变式：题目说"净赚 N 分"，答案线路走完时的账面就必须正好是 N 分。

    这条是防止"标称值和线路对不上"的最后一道闸：线路被截断过、收益又要求扛过对手应手，
    两个机制只要有一个写错，界面上就会出现"写着赚 3 分、摆出来只有 1 分"的题。
    """
    from analysis.board import find_move_by_uci, material_balance

    cases = [
        # 直接吃回被白吃的马
        make_review([make_move()]),
        # 安静的一步叉住车和后
        make_review(
            [
                make_move(
                    fen_before=QUIET_FORK,
                    best_move_uci="e4f6",
                    best_move_san="Nf6",
                    best_line_uci=["e4f6", "d5c5", "f6d7"],
                    best_line_san=["Nf6", "Qc5", "Nxd7"],
                    expected_score_before=0.9,
                )
            ]
        ),
        # 两步半的组合
        make_review(
            [
                make_move(
                    best_line_uci=["d1d2", "e8d8", "d2d3", "d8e8", "d3d5", "e8d8"],
                    best_line_san=["Rd2", "Kd8", "Rd3", "Ke8", "Rxd5", "Kd8"],
                )
            ]
        ),
    ]

    for review in cases:
        puzzles = extract_puzzles(review)
        assert puzzles, "这三个局面都应该出题"
        for puzzle in puzzles:
            white = puzzle.player_color.value == "white"
            board = chess.Board(puzzle.fen)
            start = material_balance(board, white)
            for uci in puzzle.solution_line_uci:
                move = find_move_by_uci(board, uci)
                assert move is not None, "答案线路里出现了走不动的着法：{}".format(uci)
                board.push(move)
            assert material_balance(board, white) - start == puzzle.material_gain
