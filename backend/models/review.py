"""Game-review models: what the review screen and the profile analytics consume."""

from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field

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


class GameReview(BaseModel):
    game_id: str
    white: str
    black: str
    result: str
    player_color: Color
    opening: Optional[str] = None
    headers: dict = Field(default_factory=dict)
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
