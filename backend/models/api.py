"""HTTP request/response schemas for the FastAPI layer."""

from typing import List, Optional

from pydantic import BaseModel, Field

from models.enums import Color
from models.explanation import GameSummaryRecord, MomentExplanation
from models.profile import ProfileSummary
from models.review import AnalysisJobStatus, GameListItem, GameReview


class AnalyzeRequest(BaseModel):
    pgn: str = Field(min_length=1, description="PGN text of exactly one game")
    player_color: Optional[Color] = Field(
        default=None, description="Side the user played; omitted means auto-detect"
    )
    max_critical_moments: Optional[int] = Field(default=None, ge=1, le=10)
    deep: bool = Field(default=True, description="Run pass 2 on critical positions")
    force: bool = Field(
        default=False,
        description="Re-analyze even when a stored review for this PGN already exists",
    )


class AnalyzeResponse(BaseModel):
    job_id: str
    game_id: str
    status: AnalysisJobStatus


class JobResponse(BaseModel):
    job: AnalysisJobStatus


class GameListResponse(BaseModel):
    games: List[GameListItem]


class GameReviewResponse(BaseModel):
    review: GameReview
    cached_explanations: int = 0


class ExplanationResponse(BaseModel):
    ply: int
    explanation: MomentExplanation


class GameSummaryResponse(BaseModel):
    game_id: str
    summary: GameSummaryRecord


class DeleteResponse(BaseModel):
    game_id: str
    deleted: bool


class EngineHealth(BaseModel):
    available: bool
    name: Optional[str] = None
    path: Optional[str] = None
    threads: int = 0
    hash_mb: int = 0
    error: Optional[str] = None


class LLMHealth(BaseModel):
    available: bool
    provider: str = "deepseek"
    model: Optional[str] = None
    base_url: Optional[str] = None


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "0.1.0"
    engine: EngineHealth
    llm: LLMHealth
    database: str = "ok"
    pass1_depth: int = 0
    pass2_depth: int = 0
    max_critical_moments: int = 0


class LineStep(BaseModel):
    """线路中的一步：走法 + 走完之后的局面，供前端逐步演示。"""

    uci: str
    san: str
    fen_after: str
    mover: Color


class LineWalk(BaseModel):
    """一条可以直接"播放"的引擎线路。"""

    kind: str  # "best"（引擎推荐）| "played"（实战）
    label_zh: str
    start_fen: str
    final_fen: str
    steps: List[LineStep] = Field(default_factory=list)
    #: 线路里的着法全部走完 = True；中途走不动 = False
    complete: bool = True
    #: True 表示引擎 PV 本来只保存了前若干步，不是数据出错
    truncated: bool = False
    ends_in_mate: bool = False


class MomentLinesResponse(BaseModel):
    ply: int
    move_number: int
    played_move_san: str
    best_move_san: Optional[str] = None
    evaluation_before: Optional[float] = None
    expected_score_before: Optional[float] = None
    best: LineWalk
    played: LineWalk


class PuzzleAttemptRequest(BaseModel):
    """一次作答：客户端只报"他走了哪一步"，对错由服务端判定。

    刻意不接受客户端传来的 ``correct``：对错要用引擎评估来判，前端既不自己算棋，
    也没有机会把"我做对了"直接写进数据库。
    """

    played_uci: str


class LLMTestResponse(BaseModel):
    """「测试 AI 连接」的结果：是否配置、是否真的调通、以及中文的下一步建议。"""

    configured: bool
    ok: bool
    model: Optional[str] = None
    message_zh: str
    detail: Optional[str] = None


class ErrorResponse(BaseModel):
    error: str
    detail: Optional[str] = None
    hint_zh: Optional[str] = None


__all__ = [
    "AnalyzeRequest",
    "AnalyzeResponse",
    "JobResponse",
    "GameListResponse",
    "GameReviewResponse",
    "ExplanationResponse",
    "GameSummaryResponse",
    "DeleteResponse",
    "HealthResponse",
    "ErrorResponse",
    "LLMTestResponse",
    "LineStep",
    "LineWalk",
    "MomentLinesResponse",
    "ProfileSummary",
]
