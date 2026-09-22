"""Player-profile aggregation.

Turns stored mistake events into "what kind of mistakes does this player repeat?".

The statistics are deliberately humble. With a handful of games, a category share is a
description of *those games*, not a diagnosis, so every weakness carries a confidence
band and wording that matches it ("目前观察到" instead of "你的稳定弱点是"), and the trend
line only appears once there are enough games to mean anything.
"""

from datetime import datetime
from typing import Dict, List, Optional

from analysis.stats import rate_per_100, two_proportion_z, wilson_interval
from analysis.thresholds import THRESHOLDS, AnalysisThresholds
from analysis.timecontrol import speed_label_zh
from models.enums import (
    DecisionErrorType,
    GamePhase,
    PHASE_LABELS_ZH,
    Severity,
    decision_error_label_zh,
    concept_label_zh,
    ConceptType,
)
from models.profile import (
    ConceptFrequency,
    NextFocus,
    PhaseBreakdown,
    ProfileSummary,
    RecurringWeakness,
    TimeControlBreakdown,
    TrendPoint,
    TrendSummary,
    WeaknessTrend,
)
from storage.repository import ProfileInput, example_moment_from_row

MAJOR_SEVERITIES = (Severity.MISTAKE, Severity.BLUNDER)

#: How many examples to keep per weakness (they double as future puzzle material).
MAX_EXAMPLES_PER_WEAKNESS = 3

#: Number of recent games compared against earlier ones for the trend line.
TREND_WINDOW = 3

#: 逐类型趋势要求两半各有的最少对局数与最少玩家着法数（玩家的着法才是分母）。
WEAKNESS_TREND_MIN_GAMES = 4
WEAKNESS_TREND_MIN_MOVES = 120

#: 同一批数据上同时检验多个错误类型时，用 Bonferroni 校正把门槛收紧。
WEAKNESS_TREND_BASE_ALPHA = 0.05


def build_profile(
    data: ProfileInput, thresholds: AnalysisThresholds = THRESHOLDS
) -> ProfileSummary:
    events = data.mistake_events
    major = [event for event in events if event.get("severity") in _major_values()]
    total_major = len(major)

    weaknesses = _build_weaknesses(data, major, total_major, thresholds)
    trends = _weakness_trends(data, weaknesses)
    for weakness in weaknesses:
        weakness.trend = trends.get(weakness.error_type, WeaknessTrend())
    phases = _build_phases(data, len(events))
    concepts = _build_concepts(data, len(events))
    trend_points, trend = _build_trend(data)

    severity_counts = data.severity_counts
    clocked = data.clocked_problem_moves
    under_pressure = data.problems_under_pressure
    return ProfileSummary(
        total_games=data.total_games,
        total_player_moves=data.total_player_moves,
        total_problems=len(events),
        blunders=int(severity_counts.get(Severity.BLUNDER.value, 0)),
        mistakes=int(severity_counts.get(Severity.MISTAKE.value, 0)),
        inaccuracies=int(severity_counts.get(Severity.INACCURACY.value, 0)),
        average_expected_score_loss=round(data.average_loss or 0.0, 4),
        weaknesses=weaknesses,
        phases=phases,
        top_concepts=concepts,
        trend=trend,
        trend_points=trend_points,
        time_controls=_build_time_controls(data),
        clocked_problem_moves=clocked,
        problems_under_pressure=under_pressure,
        under_time_pressure_share=(
            round(under_pressure / clocked, 4) if clocked else None
        ),
        clock_note_zh=_clock_note(clocked, under_pressure),
        next_focus=_build_next_focus(weaknesses),
        evidence_note_zh=_evidence_note(data, len(weaknesses)),
        sample_size_note_zh=_sample_note(data.total_games, len(events)),
        generated_at=datetime.utcnow(),
    )


def _major_values():
    return {severity.value for severity in MAJOR_SEVERITIES}


def _build_weaknesses(
    data: ProfileInput,
    major: List[Dict[str, object]],
    total_major: int,
    thresholds: AnalysisThresholds,
) -> List[RecurringWeakness]:
    grouped: Dict[str, Dict[str, object]] = {}
    for event in data.mistake_events:
        error_type = str(event.get("primary_error") or DecisionErrorType.UNKNOWN.value)
        bucket = grouped.setdefault(
            error_type,
            {
                "events": [],
                "games": set(),
                "major": 0,
                "loss_sum": 0.0,
                "severity_mix": {},
                "by_phase": {},
                "clocked": 0,
                "under_pressure": 0,
                "seen": [],
            },
        )
        events_list: List[Dict[str, object]] = bucket["events"]  # type: ignore[assignment]
        events_list.append(event)
        games: set = bucket["games"]  # type: ignore[assignment]
        games.add(str(event.get("game_id")))
        bucket["loss_sum"] = float(bucket["loss_sum"]) + float(
            event.get("expected_score_loss") or 0.0
        )
        severity = str(event.get("severity"))
        mix: Dict[str, int] = bucket["severity_mix"]  # type: ignore[assignment]
        mix[severity] = mix.get(severity, 0) + 1
        if severity in _major_values():
            bucket["major"] = int(bucket["major"]) + 1
        phase = str(event.get("phase") or "")
        by_phase: Dict[str, int] = bucket["by_phase"]  # type: ignore[assignment]
        by_phase[phase] = by_phase.get(phase, 0) + 1
        if event.get("clock_seconds") is not None:
            bucket["clocked"] = int(bucket["clocked"]) + 1
            if event.get("time_pressure"):
                bucket["under_pressure"] = int(bucket["under_pressure"]) + 1
        seen: List[datetime] = bucket["seen"]  # type: ignore[assignment]
        if event.get("game_created_at") is not None:
            seen.append(event["game_created_at"])  # type: ignore[arg-type]

    denominator = total_major if total_major else max(1, len(data.mistake_events))

    weaknesses: List[RecurringWeakness] = []
    for error_type, bucket in grouped.items():
        events_list = bucket["events"]  # type: ignore[assignment]
        games = bucket["games"]  # type: ignore[assignment]
        games_count = len(games)
        event_count = len(events_list)
        share = (int(bucket["major"]) / denominator) if denominator else 0.0
        average_loss = (
            float(bucket["loss_sum"]) / event_count if event_count else 0.0
        )
        confidence = _confidence(games_count, event_count, thresholds)
        label = decision_error_label_zh(_error_type(error_type))
        share_low, share_high = wilson_interval(int(bucket["major"]), denominator)
        seen = sorted(bucket["seen"])  # type: ignore[arg-type]
        examples = [
            example_moment_from_row(row)
            for row in sorted(
                events_list, key=lambda item: -float(item.get("expected_score_loss") or 0.0)
            )[:MAX_EXAMPLES_PER_WEAKNESS]
        ]
        weaknesses.append(
            RecurringWeakness(
                error_type=_error_type(error_type),
                label_zh=label,
                event_count=event_count,
                share=round(share, 4),
                games=games_count,
                average_expected_score_loss=round(average_loss, 4),
                severity_mix=dict(bucket["severity_mix"]),  # type: ignore[arg-type]
                confidence=confidence,
                share_low=share_low,
                share_high=share_high,
                by_phase=dict(bucket["by_phase"]),  # type: ignore[arg-type]
                under_time_pressure=int(bucket["under_pressure"]),
                clocked_events=int(bucket["clocked"]),
                first_seen=seen[0] if seen else None,
                last_seen=seen[-1] if seen else None,
                statement_zh=_statement(
                    label,
                    share,
                    games_count,
                    event_count,
                    confidence,
                    major_count=int(bucket["major"]),
                ),
                examples=examples,
            )
        )

    weaknesses.sort(
        key=lambda item: (
            -item.share,
            -item.event_count,
            -item.average_expected_score_loss,
        )
    )
    return weaknesses


def _confidence(games: int, events: int, thresholds: AnalysisThresholds) -> str:
    if games < thresholds.profile_recurring_min_games or events < thresholds.profile_recurring_min_events:
        return "insufficient"
    if games >= 8 and events >= 15:
        return "medium"
    return "low"


def _statement(
    label: str,
    share: float,
    games: int,
    events: int,
    confidence: str,
    major_count: int = 0,
) -> str:
    prefix = {
        "insufficient": "目前观察到",
        "low": "初步来看",
        "medium": "从数据看",
    }.get(confidence, "目前观察到")
    if major_count == 0:
        return "{}：{}，目前只出现在「不够精确」的着法里，还没有造成重大失误（{} 局中共 {} 次）。".format(
            prefix, label, games, events
        )
    return "{}：{}，占重大失误的 {:.0f}%（{} 局游戏中共 {} 次）。".format(
        prefix, label, share * 100, games, events
    )


def _error_type(value: str) -> DecisionErrorType:
    try:
        return DecisionErrorType(value)
    except ValueError:
        return DecisionErrorType.UNKNOWN


def _build_phases(data: ProfileInput, total_events: int) -> List[PhaseBreakdown]:
    result: List[PhaseBreakdown] = []
    by_phase = {str(row["phase"]): row for row in data.phase_counts}
    for phase in GamePhase:
        row = by_phase.get(phase.value)
        events = int(row["events"]) if row else 0
        result.append(
            PhaseBreakdown(
                phase=phase,
                label_zh=PHASE_LABELS_ZH.get(phase, phase.value),
                events=events,
                share=round(events / total_events, 4) if total_events else 0.0,
                average_expected_score_loss=round(
                    float(row["average_loss"]) if row else 0.0, 4
                ),
            )
        )
    return result


def _build_concepts(data: ProfileInput, total_events: int) -> List[ConceptFrequency]:
    result: List[ConceptFrequency] = []
    for row in data.concept_counts[:12]:
        try:
            concept = ConceptType(str(row["concept"]))
        except ValueError:
            continue
        count = int(row["count"])
        result.append(
            ConceptFrequency(
                concept=concept,
                label_zh=concept_label_zh(concept),
                count=count,
                share=round(count / total_events, 4) if total_events else 0.0,
            )
        )
    return result


def _build_trend(data: ProfileInput) -> tuple:
    # 用 .get 取值：趋势点只是展示用的，缺字段时不该让整份档案崩掉
    points = [
        TrendPoint(
            game_id=str(row.get("game_id", "")),
            created_at=row.get("created_at"),  # type: ignore[arg-type]
            average_expected_score_loss=round(float(row.get("average_loss") or 0.0), 4),
            problems=int(row.get("problems") or 0),
            blunders=int(row.get("blunders") or 0),
            label=str(row.get("label", "")),
        )
        for row in data.game_trend
    ]

    if len(points) < TREND_WINDOW * 2:
        return points, TrendSummary(
            available=False,
            statement_zh="目前只有 {} 局数据，样本不足以判断趋势（至少需要 {} 局）。".format(
                len(points), TREND_WINDOW * 2
            ),
        )

    recent = points[-TREND_WINDOW:]
    earlier = points[-TREND_WINDOW * 2 : -TREND_WINDOW]
    recent_avg = sum(point.average_expected_score_loss for point in recent) / len(recent)
    earlier_avg = sum(point.average_expected_score_loss for point in earlier) / len(earlier)
    delta = recent_avg - earlier_avg
    if delta <= -0.01:
        direction, wording = "improving", "最近 {} 局的期望得分损失比之前更低"
    elif delta >= 0.01:
        direction, wording = "worsening", "最近 {} 局的期望得分损失比之前更高"
    else:
        direction, wording = "flat", "最近 {} 局的期望得分损失与之前基本持平"

    return points, TrendSummary(
        available=True,
        statement_zh="{}（{:.3f} vs {:.3f}）。".format(
            wording.format(TREND_WINDOW), recent_avg, earlier_avg
        ),
        direction=direction,
        recent_average_loss=round(recent_avg, 4),
        earlier_average_loss=round(earlier_avg, 4),
    )


def _sample_note(total_games: int, total_events: int) -> str:
    if total_games == 0:
        return "还没有分析过对局。"
    if total_games < 3 or total_events < 5:
        return (
            "目前只分析了 {} 局、{} 个失误，样本太少，下面的分类只能作为观察，"
            "不能当作稳定结论。".format(total_games, total_events)
        )
    if total_games < 8:
        return (
            "已分析 {} 局、{} 个失误。样本量仍偏小，结论仅供参考；"
            "继续积累后趋势判断会更可靠。".format(total_games, total_events)
        )
    return "已分析 {} 局、{} 个失误，统计有一定的参考价值。".format(total_games, total_events)


# ------------------------------------------------- 时间维度与"先改哪一件"

def _split_games(data: ProfileInput) -> tuple:
    """把对局按时间顺序切成前后两半，返回 (前半 game_id 集合, 后半 game_id 集合, 每局玩家着法数)。

    趋势只在"后半"和"前半"之间比，不做滑动窗口：样本本来就不多，
    再切成更多段只会让每段都小到没法下结论。
    """
    games = [row for row in data.game_trend if row.get("game_id")]
    moves = {
        str(row["game_id"]): int(row.get("player_moves") or 0)
        for row in data.game_trend
        if row.get("game_id")
    }
    if len(games) < WEAKNESS_TREND_MIN_GAMES * 2:
        return set(), set(), moves
    middle = len(games) // 2
    early = {str(row["game_id"]) for row in games[:middle]}
    late = {str(row["game_id"]) for row in games[middle:]}
    return early, late, moves


def _weakness_trends(
    data: ProfileInput, weaknesses: List[RecurringWeakness]
) -> Dict[DecisionErrorType, WeaknessTrend]:
    """每一类错误在"后半段对局"里是变多还是变少——只在差异超过噪声时才下结论。

    分母用**玩家着自己的手数**（不是局数）：一局 20 手和一局 60 手的"每局次数"没法比。
    同时检验多个类型会放大假阳性，所以用 Bonferroni 把门槛收紧到 0.05 / 类型数，
    并把这件事写进返回里，让界面能如实说明。
    """
    early, late, moves = _split_games(data)
    compared = max(1, len(weaknesses))
    alpha = WEAKNESS_TREND_BASE_ALPHA / compared
    result: Dict[DecisionErrorType, WeaknessTrend] = {}

    early_moves = sum(moves.get(game_id, 0) for game_id in early)
    late_moves = sum(moves.get(game_id, 0) for game_id in late)

    counts: Dict[str, List[int]] = {}
    for event in data.mistake_events:
        error_type = str(event.get("primary_error") or DecisionErrorType.UNKNOWN.value)
        bucket = counts.setdefault(error_type, [0, 0])
        game_id = str(event.get("game_id"))
        if game_id in early:
            bucket[0] += 1
        elif game_id in late:
            bucket[1] += 1

    for weakness in weaknesses:
        early_events, late_events = counts.get(weakness.error_type.value, [0, 0])
        base = WeaknessTrend(
            early_events=early_events,
            late_events=late_events,
            compared_types=compared,
            significance_level=round(alpha, 5),
        )
        if not early or not late or early_moves < WEAKNESS_TREND_MIN_MOVES or late_moves < WEAKNESS_TREND_MIN_MOVES:
            base.statement_zh = (
                "样本不足：判断趋势需要前后各至少 {} 局、各 {} 手，目前是 {} 手对 {} 手。".format(
                    WEAKNESS_TREND_MIN_GAMES, WEAKNESS_TREND_MIN_MOVES, early_moves, late_moves
                )
            )
            result[weakness.error_type] = base
            continue

        test = two_proportion_z(early_events, early_moves, late_events, late_moves)
        base.early_rate = rate_per_100(early_events, early_moves)
        base.late_rate = rate_per_100(late_events, late_moves)
        if test is None:
            base.statement_zh = "样本不足，无法判断趋势。"
            result[weakness.error_type] = base
            continue

        _z, p_value = test
        base.p_value = round(p_value, 5)
        base.available = True
        if p_value > alpha:
            base.direction = "flat"
            base.statement_zh = "前后两半没有明显差别（每 100 手 {:.1f} 次 vs {:.1f} 次，p={:.2f}）。".format(
                base.early_rate, base.late_rate, p_value
            )
        elif base.late_rate < base.early_rate:
            base.direction = "improving"
            base.statement_zh = "在变少：每 100 手从 {:.1f} 次降到 {:.1f} 次（p={:.3f}，已按同时比较 {} 个类型收紧门槛）。".format(
                base.early_rate, base.late_rate, p_value, compared
            )
        else:
            base.direction = "worsening"
            base.statement_zh = "在变多：每 100 手从 {:.1f} 次升到 {:.1f} 次（p={:.3f}，已按同时比较 {} 个类型收紧门槛）。".format(
                base.early_rate, base.late_rate, p_value, compared
            )
        result[weakness.error_type] = base

    return result


def _build_time_controls(data: ProfileInput) -> List[TimeControlBreakdown]:
    """按时限分档看问题密度——回答"我是不是一快就崩"。"""
    order = {"ultrabullet": 0, "bullet": 1, "blitz": 2, "rapid": 3, "classical": 4}
    rows = sorted(
        data.time_control_counts,
        key=lambda row: order.get(str(row.get("speed")), 99),
    )
    result: List[TimeControlBreakdown] = []
    for row in rows:
        games = int(row.get("games") or 0)
        problems = int(row.get("problems") or 0)
        speed = str(row.get("speed"))
        result.append(
            TimeControlBreakdown(
                speed=speed,
                label_zh=speed_label_zh(speed),
                games=games,
                problems=problems,
                problems_per_game=round(problems / games, 2) if games else 0.0,
                average_expected_score_loss=round(float(row.get("average_loss") or 0.0), 4),
            )
        )
    return result


def _clock_note(clocked: int, under_pressure: int) -> str:
    """逐手时钟的覆盖情况：能判断就说结论，不能判断就说为什么。"""
    if clocked == 0:
        return (
            "你的对局 PGN 里没有逐步剩余时间，所以这份档案无法判断失误是否与时间紧张有关。"
            "Lichess 导出的 PGN 默认带时钟；Chess.com 导出时要勾选 Include clock times。"
        )
    share = under_pressure / clocked
    return (
        "{} 个问题着法带时钟信息，其中 {} 个（{:.0%}）发生在时间紧张时。"
        "阈值是剩余时间不足本局基本用时的 10% 或不足 20 秒，每一手都会显示实际剩余秒数。".format(
            clocked, under_pressure, share
        )
    )


def _build_next_focus(weaknesses: List[RecurringWeakness]) -> Optional[NextFocus]:
    """如果只能先改一件事，先改哪件——并给出理由和练法。

    只挑"已经有最低样本支撑"的类型（confidence 不是 insufficient）；
    一个都没有时如实返回 None，而不是硬推荐一个。
    """
    candidates = [item for item in weaknesses if item.confidence != "insufficient"]
    if not candidates:
        return None
    top = candidates[0]
    reasons = ["占重大失误的 {:.0f}%（{} 局中 {} 次）".format(top.share * 100, top.games, top.event_count)]
    if top.trend.available and top.trend.direction in ("improving", "worsening"):
        reasons.append(top.trend.statement_zh.rstrip("。"))
    if top.clocked_events and top.under_time_pressure:
        reasons.append(
            "其中 {}/{} 发生在时间紧张时".format(top.under_time_pressure, top.clocked_events)
        )
    return NextFocus(
        error_type=top.error_type,
        label_zh=top.label_zh,
        statement_zh="先改这一件：{}（{}）。".format(top.label_zh, "；".join(reasons)),
        confidence=top.confidence,
        drill_zh=_drill_for(top.error_type),
    )


def _drill_for(error_type: DecisionErrorType) -> str:
    """练法直接复用复盘里那套"下次怎么想"，保证同一件事在两处的说法一致。"""
    from coaching.render import ERROR_THINKING_PROCESS_ZH

    steps = ERROR_THINKING_PROCESS_ZH.get(error_type)
    if steps:
        return " ".join(steps)
    return "在题目训练里按这个主题刷题，练完再回真实对局看这类错误有没有变少。"


def _evidence_note(data: ProfileInput, weakness_count: int) -> str:
    """这些数字是怎么来的、边界在哪。写出来比让用户自己猜强。"""
    parts = [
        "占比的分母是「严重失误 + 失误」（{} 次），不是全部着法。".format(
            sum(1 for event in data.mistake_events if event.get("severity") in _major_values())
        ),
        "括号里的百分比区间是 95% Wilson 区间：样本越小，区间越宽，别把 30% 当成精确值。",
    ]
    if weakness_count > 1:
        parts.append(
            "趋势会同时检验 {} 个错误类型，因此把显著性门槛按 Bonferroni 收紧到 0.05/{}；"
            "没到门槛的一律写成「没有明显差别」。".format(weakness_count, weakness_count)
        )
    if data.time_control_counts:
        parts.append(
            "按时限分档用的是 PGN 的 TimeControl 头（40 回合折算，Lichess 口径）；"
            "不同时限的对手强度也不同，所以这是相关，不是因果。"
        )
    return " ".join(parts)
