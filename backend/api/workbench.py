"""Interactive analysis and saved variations, all on the local machine."""

import threading
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError

from analysis.study import export_study, initial_study, validate_study
from api.service import AnalysisService, get_service
from config import settings
from engine.live import LiveAnalysis, resource_limits
from models.workbench import SaveStudy, SearchSettings, StartSearch
from storage.models import Game, Study

router = APIRouter(prefix="/api")
_manager: Optional[LiveAnalysis] = None
_lock = threading.Lock()


def live_manager():
    global _manager
    with _lock:
        if _manager is None:
            path = settings.resolved_stockfish_path
            if path is None:
                raise HTTPException(503, "找不到 Stockfish，请先安装引擎。")
            _manager = LiveAnalysis(path)
        return _manager


def shutdown_live():
    global _manager
    with _lock:
        if _manager:
            _manager.close()
            _manager = None


@router.get("/analysis/options")
def options():
    limits = resource_limits()
    defaults = SearchSettings(threads=min(2, limits["max_threads"]), hash_mb=min(64, limits["max_hash_mb"]))
    return {**limits, "defaults": defaults.model_dump(), "available": settings.resolved_stockfish_path is not None}


@router.post("/analysis/start")
def start(request: StartSearch, manager=Depends(live_manager)):
    try:
        return manager.start(request)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/analysis/{job_id}")
def poll(job_id: str, manager=Depends(live_manager)):
    result = manager.read(job_id)
    if result is None:
        raise HTTPException(404, "分析已过期，请重新开始。")
    return result


@router.post("/analysis/{job_id}/stop")
def stop(job_id: str, manager=Depends(live_manager)):
    return {"stopped": manager.stop(job_id)}


def game_or_404(session, game_id):
    game = session.get(Game, game_id)
    if not game or not game.review_json:
        raise HTTPException(404, "找不到这盘棋的复盘。")
    return game


@router.get("/games/{game_id}/study")
def read_study(game_id: str, service: AnalysisService = Depends(get_service)):
    with service.database.session() as session:
        game = game_or_404(session, game_id)
        study = session.get(Study, game_id)
        return study.payload if study else initial_study(game)


@router.put("/games/{game_id}/study")
def save_study(game_id: str, request: SaveStudy, service: AnalysisService = Depends(get_service)):
    try:
        with service.database.session() as session:
            game = game_or_404(session, game_id)
            try:
                payload = validate_study(game, request)
            except ValueError as exc:
                raise HTTPException(422, str(exc)) from exc
            if request.revision == 0:
                session.add(Study(game_id=game_id, revision=1, payload=payload))
                session.flush()
            else:
                result = session.execute(update(Study).where(Study.game_id == game_id, Study.revision == request.revision)
                                         .values(revision=request.revision+1, payload=payload))
                if result.rowcount != 1:
                    raise HTTPException(409, "另一个页面已修改分支。请先导出当前棋谱，再刷新以读取最新版本。")
        return payload
    except IntegrityError as exc:
        raise HTTPException(409, "另一个页面已保存分支。请先导出当前棋谱，再刷新。") from exc


@router.get("/games/{game_id}/study.pgn", response_class=PlainTextResponse)
def download_study(game_id: str, service: AnalysisService = Depends(get_service)):
    with service.database.session() as session:
        game = game_or_404(session, game_id)
        study = session.get(Study, game_id)
        return export_study(game, study.payload if study else initial_study(game))
