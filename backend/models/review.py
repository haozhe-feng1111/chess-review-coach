"""Game-review models: what the review screen and the profile analytics consume."""

from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field

from models.game import TimeControl
from models.enums import (
    AnalysisStatus,
    Color,
    ConceptType,
    DecisionErrorType,
    GamePhase,
    Severity,
)
from models.evidence import AnalysisEvidence


class CriticalityReason(str, Enum):
    """Why a position was promoted into the review section."""

    HIGH_LOSS = "high_loss"
    SIGN_FLIP = "sign_flip"
    MISSED_WIN = "missed_win"
    MATE_APPEARS = "mate_appears"
    MATE_DISAPPEARS = "mate_disappears"
    POSITION_COLLAPSE = "position_collapse"
    FORCED_SEQUENCE = "forced_sequence"
    UNIQUE_BEST_MOVE = "unique_best_move"


CRITICALITY_REASON_LABELS_ZH = {
    CriticalityReason.HIGH_LOSS: "期望得分损失大",
    CriticalityReason.SIGN_FLIP: "局面优劣反转",
    CriticalityReason.MISSED_WIN: "漏掉胜机",
    CriticalityReason.MATE_APPEARS: "对手出现杀棋",
    CriticalityReason.MATE_DISAPPEARS: "自己的杀棋消失",
    CriticalityReason.POSITION_COLLAPSE: "胜负逆转",
    CriticalityReason.FORCED_SEQUENCE: "进入强制序列",
    CriticalityReason.UNIQUE_BEST_MOVE: "唯一好棋",
}


class MoveAssessment(BaseModel):
    """Lightweight per-ply record backing the move list and the eval graph.

    ``best_move_*`` is filled for **every** move, not just the critical ones: the review
    always shows what the engine wanted, and only the critical few get a full
    explanation. ``best_move_uci`` is legal in ``fen_before`` — never in ``fen_after``.
    """

    ply: int
    move_number: int
    color: Color
    san: str
    uci: str
    fen_before: str
    fen_after: str
    is_player_move: bool
    severity: Optional[Severity] = None
    expected_score_loss: Optional[float] = None
    # Evaluation of the position *after* this move, player perspective.
    evaluation_after: Optional[float] = None
    mate_after: Optional[int] = None
    #: 引擎在走子前看到的杀棋（正数 = 玩家可以 N 步将杀）。出题要靠它。
    mate_before: Optional[int] = None
    #: 走完这一手之后剩余的时间（秒），来自 PGN 的 ``[%clk]`` 注释。
    #: 没有就是 None——这一项从来不靠估。
    clock_seconds: Optional[float] = None
    #: 是否时间紧张。None = 这盘棋的 PGN 没有时钟信息，无从判断。
    time_pressure: Optional[bool] = None
    # --- engine recommendation for the position this move was played in ---
    best_move_san: Optional[str] = None
    best_move_uci: Optional[str] = None
    #: True when the move played *is* the engine's first choice.
    is_engine_best: bool = False
    #: Evaluation of the position before the move (player perspective).
    evaluation_before: Optional[float] = None
    expected_score_before: Optional[float] = None
    # --- 后续线路：可以在棋盘上逐步演示，然后回到实战 ---
    #: 引擎推荐着法及其后续（第一个元素就是 best_move_uci）。
    best_line_uci: List[str] = Field(default_factory=list)
    best_line_san: List[str] = Field(default_factory=list)
    #: 实战着法及其后续（第一个元素就是本手的 uci）。
    played_line_uci: List[str] = Field(default_factory=list)
    played_line_san: List[str] = Field(default_factory=list)
    concept_tags: List[ConceptType] = Field(default_factory=list)
    decision_error_tags: List[DecisionErrorType] = Field(default_factory=list)
    #: 置信度最高的决策失误原因（``decision_error_tags`` 已经按置信度排序）。
    #: 单独存一份，是因为档案按它做聚合：早先这份聚合依赖"这一手是不是关键局面"，
    #: 而一盘棋只有几个关键局面，导致大量失误被记成"原因不明确"。
    primary_error: Optional[DecisionErrorType] = None
    primary_error_confidence: Optional[float] = None
    is_critical: bool = False


class CriticalMoment(BaseModel):
    """A position worth reviewing, with everything needed to re-ask "best move?".

    ``fen`` + ``solution_uci`` are kept explicitly (rather than only inside
    ``evidence``) so a future puzzle trainer can build items from a player's own
    games without re-deriving anything.
    """

    ply: int
    move_number: int
    player_color: Color
    phase: GamePhase
    severity: Severity
    criticality_score: float
    reasons: List[CriticalityReason] = Field(default_factory=list)
    one_liner_zh: str = ""
    fen: str
    played_move_san: str
    solution_uci: Optional[str] = None
    solution_san: Optional[str] = None
    evidence: AnalysisEvidence


class MoveCounts(BaseModel):
    best: int = 0
    excellent: int = 0
    good: int = 0
    inaccuracy: int = 0
    mistake: int = 0
    blunder: int = 0

    @property
    def problems(self) -> int:
        return self.inaccuracy + self.mistake + self.blunder


class PhaseStats(BaseModel):
    phase: GamePhase
    moves: int = 0
    problems: int = 0
    average_expected_score_loss: float = 0.0


class EngineMeta(BaseModel):
    """Which engine settings produced this analysis (shown in the evidence panel)."""

    engine_name: str = "unknown"
    pass1_depth: int = 0
    pass1_nodes: int = 0
    pass2_depth: int = 0
    pass2_multipv: int = 0
    threads: int = 0
    hash_mb: int = 0
    positions_analyzed: int = 0
    cache_hits: int = 0
    elapsed_seconds: float = 0.0
    complete: bool = True
    warnings: List[str] = Field(default_factory=list)


class TimePressureMoment(BaseModel):
    """一个发生在时间紧张时的问题着法（附上真实剩余秒数）。"""

    ply: int
    move_number: int
    san: str
    clock_seconds: float
    severity: Optional[Severity] = None
    expected_score_loss: Optional[float] = None


class TimePressureSummary(BaseModel):
    """单局的时间归因：问题着法有多少发生在时间紧张时。

    ``available=False`` 表示这盘棋的 PGN 没有逐手时钟——这时**什么都不说**，
    而不是写一句"可能和时间有关"。这正是原来那个 TIME_PRESSURE_UNKNOWN 想表达的意思，
    现在它有了确定的答案：要么有数据（能判），要么没有（如实说没有）。
    """

    available: bool = False
    limit_seconds: Optional[float] = None
    problem_moves: int = 0
    under_pressure: int = 0
    share: float = 0.0
    moments: List[TimePressureMoment] = Field(default_factory=list)
    #: 默认就是一句真话：早期存的复盘没有这个字段，界面不能因此显示空白
    statement_zh: str = "这盘棋没有携带时间信息，无法判断失误是否与时间紧张有关。"


class GameReview(BaseModel):
    game_id: str
    white: str
    black: str
    result: str
    player_color: Color
    opening: Optional[str] = None
    headers: dict = Field(default_factory=dict)
    #: 本局的时间设置（来自 PGN 头）。没有 TimeControl 时是 None。
    time_control: Optional[TimeControl] = None
    #: 这盘棋的 PGN 是否带逐手时钟（决定能不能做时间压力归因）。
    has_clocks: bool = False
    time_pressure: "TimePressureSummary" = Field(default_factory=lambda: TimePressureSummary())
    moves: List[MoveAssessment] = Field(default_factory=list)
    critical_moments: List[CriticalMoment] = Field(default_factory=list)
    counts: MoveCounts = Field(default_factory=MoveCounts)
    average_expected_score_loss: float = 0.0
    phase_stats: List[PhaseStats] = Field(default_factory=list)
    engine: EngineMeta = Field(default_factory=EngineMeta)
    llm_available: bool = False
    status: AnalysisStatus = AnalysisStatus.COMPLETED
    warnings: List[str] = Field(default_factory=list)
    created_at: Optional[datetime] = None


class GameListItem(BaseModel):
    game_id: str
    white: str
    black: str
    result: str
    player_color: Color
    opening: Optional[str] = None
    created_at: Optional[datetime] = None
    move_count: int = 0
    blunders: int = 0
    mistakes: int = 0
    inaccuracies: int = 0
    average_expected_score_loss: float = 0.0


class AnalysisJobStatus(BaseModel):
    job_id: str
    game_id: Optional[str] = None
    status: AnalysisStatus
    progress: float = 0.0
    message_zh: str = ""
    error: Optional[str] = None
    review: Optional[GameReview] = None
