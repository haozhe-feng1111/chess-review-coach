"""HTTP routes.

Thin wrappers over :class:`api.service.AnalysisService`. Errors are translated into
responses that carry a Chinese hint, because the person reading them is a chess player,
not a developer.
"""

import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query

from api.service import AnalysisService, get_service
from engine.errors import EngineError, PgnError
from models.api import (
    AnalyzeRequest,
    PuzzleAttemptRequest,
    LLMTestResponse,
    MomentLinesResponse,
    AnalyzeResponse,
    DeleteResponse,
    ExplanationResponse,
    GameListResponse,
    GameReviewResponse,
    GameSummaryResponse,
    HealthResponse,
    JobResponse,
)
from models.profile import ProfileSummary
from models.puzzle import (
    Puzzle,
    PuzzleAttemptResult,
    PuzzleDetail,
    PuzzleStats,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")


def service() -> AnalysisService:
    return get_service()


@router.get("/health", response_model=HealthResponse)
def health(svc: AnalysisService = Depends(service)) -> HealthResponse:
    engine = svc.engine_health()
    llm = svc.llm_health()
    config = svc.public_config()
    return HealthResponse(
        status="ok" if engine["available"] else "degraded",
        engine=engine,  # type: ignore[arg-type]
        llm=llm,  # type: ignore[arg-type]
        pass1_depth=config["pass1_depth"],  # type: ignore[arg-type]
        pass2_depth=config["pass2_depth"],  # type: ignore[arg-type]
        max_critical_moments=config["max_critical_moments"],  # type: ignore[arg-type]
    )


@router.post("/llm/test", response_model=LLMTestResponse)
def test_llm(svc: AnalysisService = Depends(service)) -> LLMTestResponse:
    """真实调用一次 DeepSeek，用于验证 API Key 是否可用。"""
    return LLMTestResponse(**svc.test_llm())  # type: ignore[arg-type]


@router.post("/games/analyze", response_model=AnalyzeResponse)
def analyze(
    request: AnalyzeRequest, svc: AnalysisService = Depends(service)
) -> AnalyzeResponse:
    try:
        result = svc.start_analysis(
            pgn=request.pgn,
            player_color=request.player_color,
            max_critical_moments=request.max_critical_moments,
            deep=request.deep,
            force=request.force,
        )
    except PgnError as exc:
        raise HTTPException(
            status_code=exc.http_status,
            detail={"error": exc.message, "detail": exc.detail, "hint_zh": exc.hint_zh},
        ) from exc
    except EngineError as exc:
        raise HTTPException(
            status_code=exc.http_status,
            detail={"error": exc.message, "detail": exc.detail, "hint_zh": exc.hint_zh},
        ) from exc
    return AnalyzeResponse(
        job_id=result.job_id, game_id=result.game_id, status=result.status
    )


@router.get("/jobs/{job_id}", response_model=JobResponse)
def job_status(job_id: str, svc: AnalysisService = Depends(service)) -> JobResponse:
    status = svc.job_status(job_id)
    if status is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "job not found", "hint_zh": "找不到这个分析任务，请重新提交。"},
        )
    return JobResponse(job=status)


@router.get("/games", response_model=GameListResponse)
def list_games(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    svc: AnalysisService = Depends(service),
) -> GameListResponse:
    return GameListResponse(games=svc.list_games(limit=limit, offset=offset))


@router.get("/games/{game_id}", response_model=GameReviewResponse)
def get_game(game_id: str, svc: AnalysisService = Depends(service)) -> GameReviewResponse:
    review = svc.get_review(game_id)
    if review is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "game not found", "hint_zh": "找不到这盘棋的分析结果。"},
        )
    return GameReviewResponse(review=review)


@router.get(
    "/games/{game_id}/moments/{ply}/explanation", response_model=ExplanationResponse
)
def explain_moment(
    game_id: str, ply: int, svc: AnalysisService = Depends(service)
) -> ExplanationResponse:
    explanation = svc.explain_moment(game_id, ply)
    if explanation is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "moment not found",
                "hint_zh": "这盘棋里没有这个关键局面，可能该局面不严重或尚未分析。",
            },
        )
    return ExplanationResponse(ply=ply, explanation=explanation)


@router.get("/games/{game_id}/moves/{ply}/lines", response_model=MomentLinesResponse)
@router.get(
    "/games/{game_id}/moments/{ply}/lines",
    response_model=MomentLinesResponse,
    include_in_schema=False,
)
def moment_lines(
    game_id: str, ply: int, svc: AnalysisService = Depends(service)
) -> MomentLinesResponse:
    """返回该局面的引擎线路与实战线路，供前端逐步演示（任何一手都可以查）。"""
    lines = svc.moment_lines(game_id, ply)
    if lines is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "moment not found",
                "hint_zh": "这盘棋里没有这个关键局面，可能该局面不严重或尚未分析。",
            },
        )
    return lines


@router.get("/games/{game_id}/summary", response_model=GameSummaryResponse)
def game_summary(
    game_id: str, svc: AnalysisService = Depends(service)
) -> GameSummaryResponse:
    result = svc.game_summary(game_id)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "game not found", "hint_zh": "找不到这盘棋的分析结果。"},
        )
    _review, summary = result
    return GameSummaryResponse(game_id=game_id, summary=summary)


@router.delete("/games/{game_id}", response_model=DeleteResponse)
def delete_game(game_id: str, svc: AnalysisService = Depends(service)) -> DeleteResponse:
    deleted = svc.delete_game(game_id)
    return DeleteResponse(game_id=game_id, deleted=deleted)


@router.get("/puzzles", response_model=List[Puzzle])
def list_puzzles(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    kind: Optional[str] = Query(default=None, pattern="^(mate|material)$"),
    theme: Optional[str] = Query(default=None),
    game_id: Optional[str] = Query(default=None),
    svc: AnalysisService = Depends(service),
) -> List[Puzzle]:
    """题目列表。只包含有强制走法的局面（将杀 / 赚子）。"""
    return svc.list_puzzles(limit=limit, offset=offset, kind=kind, theme=theme, game_id=game_id)


@router.get("/puzzles/stats", response_model=PuzzleStats)
def puzzles_stats(svc: AnalysisService = Depends(service)) -> PuzzleStats:
    return svc.puzzle_stats()


@router.get("/puzzles/{puzzle_id}", response_model=PuzzleDetail)
def puzzle_detail(
    puzzle_id: str, svc: AnalysisService = Depends(service)
) -> PuzzleDetail:
    """题目详情：含展开好的答案线路（每一步之后的局面），前端直接播放。"""
    detail = svc.get_puzzle_detail(puzzle_id)
    if detail is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "puzzle not found", "hint_zh": "找不到这道题目。"},
        )
    return detail


@router.post("/puzzles/{puzzle_id}/attempt", response_model=PuzzleAttemptResult)
def puzzle_attempt(
    puzzle_id: str, request: PuzzleAttemptRequest, svc: AnalysisService = Depends(service)
) -> PuzzleAttemptResult:
    """记录一次作答：客户端只说他走了哪一步，对错由服务端用引擎判定。"""
    try:
        result = svc.grade_puzzle_attempt(puzzle_id, request.played_uci)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={"error": "illegal move", "hint_zh": str(exc)},
        )
    if result is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "puzzle not found", "hint_zh": "找不到这道题目。"},
        )
    return result


@router.get("/profile", response_model=ProfileSummary)
def profile(svc: AnalysisService = Depends(service)) -> ProfileSummary:
    return svc.profile()


@router.get("/config")
def public_config(svc: AnalysisService = Depends(service)) -> dict:
    """Non-secret configuration the UI shows (engine budget, LLM availability)."""
    return svc.public_config()


__all__ = ["router"]
