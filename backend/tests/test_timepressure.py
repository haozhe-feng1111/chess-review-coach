"""时间压力归因的测试。

规则很简单，但结论会被写在界面上（"3/4 个问题着法发生在时间紧张时"），
所以正例、反例、以及"没有数据时绝不猜"这三种情况都要测。
"""

import pytest

from analysis.timepressure import build_time_pressure_summary, under_time_pressure
from analysis.timecontrol import parse_time_control
from models.enums import Color, Severity
from models.review import MoveAssessment

BLITZ = parse_time_control({"TimeControl": "300"})       # 5 分钟 → 阈值 max(20, 30) = 30 秒
BULLET = parse_time_control({"TimeControl": "60"})        # 1 分钟 → 阈值仍取下限 20 秒
CLASSICAL = parse_time_control({"TimeControl": "1800"})   # 30 分钟 → 阈值 180 秒


def move(
    ply: int,
    *,
    clock: float = None,
    severity: Severity = Severity.MISTAKE,
    is_player: bool = True,
    loss: float = 0.4,
    san: str = "Qh5",
) -> MoveAssessment:
    return MoveAssessment(
        ply=ply,
        move_number=(ply + 1) // 2,
        color=Color.WHITE if ply % 2 == 1 else Color.BLACK,
        san=san,
        uci="d1h5",
        fen_before="before",
        fen_after="after",
        is_player_move=is_player,
        severity=severity,
        expected_score_loss=loss,
        clock_seconds=clock,
        time_pressure=under_time_pressure(clock, BLITZ.base_seconds) if clock else None,
    )


def test_threshold_uses_the_wider_of_percentage_and_floor():
    # 5 分钟棋：10% = 30 秒 > 20 秒下限 → 用 30 秒
    assert under_time_pressure(30.0, BLITZ.base_seconds) is True
    assert under_time_pressure(31.0, BLITZ.base_seconds) is False
    # 1 分钟棋：10% = 6 秒 < 20 秒下限 → 用 20 秒，否则每一步都算时间紧张
    assert under_time_pressure(19.0, BULLET.base_seconds) is True
    assert under_time_pressure(21.0, BULLET.base_seconds) is False
    # 30 分钟棋：10% = 180 秒
    assert under_time_pressure(120.0, CLASSICAL.base_seconds) is True
    assert under_time_pressure(600.0, CLASSICAL.base_seconds) is False


def test_without_a_clock_there_is_no_answer():
    assert under_time_pressure(None, BLITZ.base_seconds) is None


def test_summary_counts_only_problem_moves_under_pressure():
    moves = [
        move(1, clock=280.0, severity=Severity.GOOD),   # 不是问题着法 → 不参与统计
        move(3, clock=200.0, severity=Severity.BEST),
        move(5, clock=25.0, san="Qh5"),            # 问题着法 + 时间紧张 ✓
        move(6, clock=210.0, is_player=False),     # 对手的着法永远不算
        move(7, clock=150.0, san="Bb5"),           # 问题着法，但时间充足 ✗
        move(9, clock=12.0, san="Nf3"),            # 问题着法 + 时间紧张 ✓
    ]
    summary = build_time_pressure_summary(moves, BLITZ)
    assert summary.available is True
    assert summary.problem_moves == 3
    assert summary.under_pressure == 2
    assert summary.share == pytest.approx(0.6667, abs=0.001)
    assert [moment.san for moment in summary.moments] == ["Qh5", "Nf3"]
    assert "2/3" in summary.statement_zh
    assert "剩 25 秒" in summary.statement_zh


def test_summary_says_the_problem_was_not_time_when_the_clock_was_healthy():
    """有数据、而且时间很充裕时，要敢下"不是时间问题"这个结论。"""
    summary = build_time_pressure_summary(
        [move(5, clock=180.0), move(7, clock=240.0)], BLITZ
    )
    assert summary.under_pressure == 0
    assert "不在时间上" in summary.statement_zh


def test_summary_is_honest_when_the_pgn_has_no_clocks():
    """没有时钟信息时只说"没有数据"，不给任何倾向性的话。"""
    summary = build_time_pressure_summary([move(5, clock=None), move(7, clock=None)], BLITZ)
    assert summary.available is False
    assert summary.under_pressure == 0
    assert summary.moments == []
    assert "没有每步剩余时间" in summary.statement_zh
    assert "Include clock times" in summary.statement_zh


def test_summary_with_no_problem_moves_does_not_divide_by_zero():
    summary = build_time_pressure_summary([move(1, clock=200.0, severity=Severity.BEST)], BLITZ)
    assert summary.problem_moves == 0
    assert summary.share == 0.0
    # 没有"问题着法"可统计 → 如实说这一局没有可归因的东西
    assert summary.available is True
    assert summary.under_pressure == 0
    assert "没有需要复盘的问题着法" in summary.statement_zh


def test_summary_without_a_time_control_header_falls_back_to_the_floor():
    """没有 TimeControl 头时阈值退回 20 秒下限，而不是崩掉或猜一个分档出来。"""
    summary = build_time_pressure_summary([move(5, clock=15.0)], None)
    assert summary.limit_seconds == 20.0
    assert summary.under_pressure == 1


def test_summary_uses_the_games_own_base_time():
    summary = build_time_pressure_summary([move(5, clock=25.0)], BLITZ)
    assert summary.limit_seconds == 30.0  # 5 分钟棋：10% = 30 秒
    assert summary.under_pressure == 1
