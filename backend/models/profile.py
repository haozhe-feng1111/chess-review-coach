"""Long-term player-profile models.

Sample-size honesty is encoded in the data model: every recurring weakness carries a
confidence band and a ready-made Chinese sentence, so the UI cannot accidentally
claim "your stable weakness is X" after two games.
"""

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from models.enums import ConceptType, DecisionErrorType, GamePhase, Severity


class WeaknessTrend(BaseModel):
    """某一类错误是不是在变少——只有在差异超过噪声时才敢下结论。"""

    available: bool = False
    direction: str = "unknown"  # improving | worsening | flat | unknown
    statement_zh: str = ""
    #: 每 100 手玩家着法里出现该类问题的次数（比"每局几次"稳，因为对局长度不一）
    early_rate: Optional[float] = None
    late_rate: Optional[float] = None
    early_events: int = 0
    late_events: int = 0
    p_value: Optional[float] = None
    #: 同时比较了多少个错误类型（多重比较校正用，写出来让用户知道门槛被收紧了）
    compared_types: int = 0
    significance_level: float = 0.05


class ExampleMoment(BaseModel):
    """A stored position the profile can show (and a future trainer can reuse)."""

    game_id: str
    ply: int
    move_number: int
    san: str
    opponent: str = ""
    severity: Severity
    one_liner_zh: str = ""
    fen: str = ""
    solution_san: Optional[str] = None


class RecurringWeakness(BaseModel):
    error_type: DecisionErrorType
    label_zh: str
    event_count: int
    share: float
    games: int
    average_expected_score_loss: float
    severity_mix: Dict[str, int] = Field(default_factory=dict)
    # "insufficient" | "low" | "medium" — never claim more than the data supports.
    confidence: str = "insufficient"
    statement_zh: str = ""
    #: 占比的 95% Wilson 区间——没有区间的百分比会让人高估小样本的确定性
    share_low: float = 0.0
    share_high: float = 0.0
    #: phase value -> 次数
    by_phase: Dict[str, int] = Field(default_factory=dict)
    #: 这一类错误里有多少发生在时间紧张时（clocked = 其中有多少个能判断）
    under_time_pressure: int = 0
    clocked_events: int = 0
    first_seen: Optional[datetime] = None
    last_seen: Optional[datetime] = None
    trend: WeaknessTrend = Field(default_factory=WeaknessTrend)
    examples: List[ExampleMoment] = Field(default_factory=list)


class PhaseBreakdown(BaseModel):
    phase: GamePhase
    label_zh: str
    events: int
    share: float
    average_expected_score_loss: float


class ConceptFrequency(BaseModel):
    concept: ConceptType
    label_zh: str
    count: int
    share: float


class TrendPoint(BaseModel):
    game_id: str
    created_at: Optional[datetime] = None
    average_expected_score_loss: float = 0.0
    problems: int = 0
    blunders: int = 0
    label: str = ""


class TrendSummary(BaseModel):
    """Only computed when there are enough games to say anything at all."""

    available: bool = False
    statement_zh: str = ""
    direction: str = "flat"  # "improving" | "worsening" | "flat"
    recent_average_loss: Optional[float] = None
    earlier_average_loss: Optional[float] = None


class TimeControlBreakdown(BaseModel):
    """按时限分档看问题着法的密度（数据来自 PGN 的 TimeControl 头）。"""

    speed: str
    label_zh: str
    games: int = 0
    problems: int = 0
    problems_per_game: float = 0.0
    average_expected_score_loss: float = 0.0


class NextFocus(BaseModel):
    """如果只能先改一件事，先改这个——以及为什么是它。"""

    error_type: DecisionErrorType
    label_zh: str
    statement_zh: str = ""
    confidence: str = "insufficient"
    drill_zh: str = ""


class ProfileSummary(BaseModel):
    total_games: int = 0
    total_player_moves: int = 0
    total_problems: int = 0
    blunders: int = 0
    mistakes: int = 0
    inaccuracies: int = 0
    average_expected_score_loss: float = 0.0
    weaknesses: List[RecurringWeakness] = Field(default_factory=list)
    phases: List[PhaseBreakdown] = Field(default_factory=list)
    top_concepts: List[ConceptFrequency] = Field(default_factory=list)
    trend: TrendSummary = Field(default_factory=TrendSummary)
    trend_points: List[TrendPoint] = Field(default_factory=list)
    time_controls: List[TimeControlBreakdown] = Field(default_factory=list)
    #: 逐手时钟的覆盖情况："有多少问题着法能判断时间压力"以及其中紧张的比例
    clocked_problem_moves: int = 0
    problems_under_pressure: int = 0
    under_time_pressure_share: Optional[float] = None
    clock_note_zh: str = ""
    next_focus: Optional[NextFocus] = None
    sample_size_note_zh: str = ""
    #: 这些数字是怎么算出来的、边界在哪（分母、多重比较校正、时间压力的阈值……）
    evidence_note_zh: str = ""
    generated_at: Optional[datetime] = None
