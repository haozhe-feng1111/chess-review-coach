"""时间压力归因：这一手是不是在时间紧张时走的，以及一局里有多少问题着法发生在时间紧张时。

这件事以前在界面上只有一句"PGN 中没有时间信息，无法判断是否与时间紧张有关"
（``DecisionErrorType.TIME_PRESSURE_UNKNOWN``）。现在有三个确定的答案：

* **有逐手时钟** → 给出**是/否**，并附上实际剩余秒数；
* **没有逐手时钟** → 如实说"没有数据"，而不是猜；
* **有 PGN 的 TimeControl 头** → 至少知道本局是子弹/超快棋/快棋/慢棋（见 analysis.timecontrol）。

时间压力刻意**不做**决策失误分类里的一个类型（不参与 ``primary_error``）：
它是"当时的条件"，不是"你想错了什么"。如果混进去，"时间紧张"会把
"没检查对手的强制手"这类真正要改的原因挤出榜首。
"""

from typing import List, Optional

from analysis.thresholds import THRESHOLDS, AnalysisThresholds
from models.game import TimeControl
from models.review import MoveAssessment, TimePressureMoment, TimePressureSummary


def under_time_pressure(
    clock_seconds: Optional[float],
    base_seconds: Optional[int],
    thresholds: AnalysisThresholds = THRESHOLDS,
) -> Optional[bool]:
    """剩余时间是否低于阈值；没有时钟数据时返回 None（不知道）。"""
    if clock_seconds is None:
        return None
    return clock_seconds <= thresholds.time_pressure.limit_for(base_seconds)


def build_time_pressure_summary(
    assessments: List[MoveAssessment],
    time_control: Optional[TimeControl],
    thresholds: AnalysisThresholds = THRESHOLDS,
) -> TimePressureSummary:
    """把"问题着法里有多少发生在时间紧张时"算成一句可核实的话。

    统计口径只看**有时钟数据的那些问题着法**，并把覆盖率一起报出来：
    PGN 只注释了一部分时，结论要限定在那部分上，不能假装覆盖了全部。
    """
    base = time_control.base_seconds if time_control else None
    limit = thresholds.time_pressure.limit_for(base)

    problems = [
        move
        for move in assessments
        if move.is_player_move and move.severity is not None and move.severity.is_problem
    ]
    timed = [move for move in problems if move.clock_seconds is not None]

    if not any(move.clock_seconds is not None for move in assessments):
        return TimePressureSummary(
            available=False,
            limit_seconds=limit,
            problem_moves=len(problems),
            statement_zh=(
                "这盘棋的 PGN 里没有每步剩余时间（Chess.com 导出时要勾选 Include clock times，"
                "Lichess 默认就带），所以无法判断失误是否与时间紧张有关。"
            ),
        )

    if not problems:
        return TimePressureSummary(
            available=True,
            limit_seconds=limit,
            statement_zh="这盘棋没有需要复盘的问题着法（时钟信息已记录，但没有可归因的东西）。",
        )

    pressed = [move for move in timed if move.time_pressure]
    moments = [
        TimePressureMoment(
            ply=move.ply,
            move_number=move.move_number,
            san=move.san,
            clock_seconds=float(move.clock_seconds or 0.0),
            severity=move.severity,
            expected_score_loss=move.expected_score_loss,
        )
        for move in sorted(
            pressed, key=lambda item: item.expected_score_loss or 0.0, reverse=True
        )
    ]

    coverage = (
        "（{} 个有问题着法，其中 {} 个带时钟信息）".format(len(problems), len(timed))
        if len(timed) < len(problems)
        else ""
    )
    if pressed:
        statement = "{}/{} 个问题着法发生在时间紧张时（剩余时间 ≤ {:g} 秒）：{}".format(
            len(pressed),
            len(problems),
            limit,
            "、".join(
                "第 {} 回合 {}（剩 {:g} 秒）".format(
                    moment.move_number, moment.san, moment.clock_seconds
                )
                for moment in moments[:3]
            ),
        )
    else:
        statement = (
            "{} 个问题着法都不是在时间紧张时走的（剩余时间都多于 {:g} 秒）"
            "——这盘棋的问题不在时间上。".format(len(timed), limit)
        )
    statement += coverage

    return TimePressureSummary(
        available=True,
        limit_seconds=limit,
        problem_moves=len(timed),
        under_pressure=len(pressed),
        share=round(len(pressed) / len(timed), 4) if timed else 0.0,
        moments=moments,
        statement_zh=statement,
    )
