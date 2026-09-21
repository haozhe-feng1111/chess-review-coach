"""Application service: parses, queues, analyzes, persists, explains.

The FastAPI routes are thin wrappers over this class. Keeping the orchestration here
means the HTTP layer never touches the engine, the database or the LLM directly, and the
whole pipeline stays testable without a web server.

Analysis is queued on a single worker thread because one Stockfish process serves one
game at a time; that keeps laptop resource usage predictable and avoids engine
thrashing. Jobs report progress through a polled status endpoint.
"""

import logging
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from analysis.lines import walk_line
from analysis.pgn import count_games, parse_pgn
from analysis.pipeline import GameAnalyzer, PipelineConfig
from analysis.profile import build_profile
from coaching.explainer import CoachExplainer
from coaching.provider import build_provider, humanize_error
from coaching.render import one_liner_zh
from config import settings as default_settings
from engine.errors import EngineError, EngineNotFoundError, PgnError
from engine.stockfish import EngineConfig, EngineIdentity, StockfishEngine, probe_engine
from models.api import MomentLinesResponse
from models.enums import AnalysisStatus, Color
from models.explanation import GameSummaryRecord, MomentExplanation
from models.profile import ProfileSummary
from models.review import AnalysisJobStatus, GameListItem, GameReview
from storage.cache import SqliteAnalysisCache, SqliteExplanationCache
from storage.db import Database, get_database
from storage.repository import (
    collect_profile_input,
    get_job as get_job_row,
    delete_game as repo_delete_game,
    get_review,
    known_player_names,
    list_games,
    make_game_id,
    save_review,
    upsert_job,
)

logger = logging.getLogger(__name__)

#: 引擎 PV 在证据里保存的步数上限（与 engine.stockfish.PV_MAX_PLIES 保持一致）。
PV_STORED_PLIES = 12


@dataclass
class StartResult:
    job_id: str
    game_id: str
    status: AnalysisJobStatus


class AnalysisService:
    def __init__(
        self,
        database_url: Optional[str] = None,
        database: Optional[Database] = None,
        settings=default_settings,
    ) -> None:
        self._settings = settings
        self._db = database if database is not None else get_database(database_url)
        self._engine: Optional[StockfishEngine] = None
        self._engine_lock = threading.Lock()
        self._engine_identity: Optional[EngineIdentity] = None
        self._engine_error: Optional[str] = None

        self._analysis_cache = SqliteAnalysisCache(self._db)
        self._explanation_cache = SqliteExplanationCache(self._db)
        # Keep the position cache bounded on a local machine; pruning only kicks in once
        # the table exceeds its cap, so this is a single cheap query on startup.
        try:
            removed = self._analysis_cache.prune()
            if removed:
                logger.info("Pruned %s expired analysis cache entries", removed)
        except Exception:  # pragma: no cover - never block startup on maintenance
            logger.warning("Could not prune the analysis cache", exc_info=True)
        self._provider = build_provider(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
            model=settings.deepseek_model,
            timeout=settings.llm_timeout,
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
        )
        self._coach = CoachExplainer(self._provider, self._explanation_cache)

        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="analysis")
        self._jobs: Dict[str, AnalysisJobStatus] = {}
        self._jobs_lock = threading.Lock()

    # ---------------------------------------------------------------- lifecycle

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False)
        with self._engine_lock:
            if self._engine is not None:
                self._engine.close()
                self._engine = None

    @property
    def coach(self) -> CoachExplainer:
        return self._coach

    @property
    def database(self) -> Database:
        return self._db

    # ------------------------------------------------------------------- health

    def engine_config(self) -> EngineConfig:
        path = self._settings.resolved_stockfish_path
        if path is None:
            raise EngineNotFoundError("Stockfish binary was not found")
        return EngineConfig(
            path=path,
            threads=self._settings.effective_threads,
            hash_mb=self._settings.stockfish_hash_mb,
            startup_timeout=self._settings.engine_startup_timeout,
        )

    def ensure_engine(self) -> StockfishEngine:
        """Start Stockfish on first use; surfaced to /health when it fails."""
        with self._engine_lock:
            if self._engine is not None:
                return self._engine
            config = self.engine_config()
            engine = StockfishEngine(config)
            try:
                engine.start()
            except EngineError as exc:
                self._engine_error = exc.message
                raise
            self._engine = engine
            self._engine_identity = EngineIdentity(name=engine.name, path=str(config.path))
            self._engine_error = None
            return engine

    def engine_health(self) -> Dict[str, object]:
        try:
            engine = self.ensure_engine()
            return {
                "available": True,
                "name": engine.name,
                "path": str(self._settings.resolved_stockfish_path or ""),
                "threads": self._settings.effective_threads,
                "hash_mb": self._settings.stockfish_hash_mb,
                "error": None,
            }
        except EngineError as exc:
            return {
                "available": False,
                "name": None,
                "path": str(self._settings.resolved_stockfish_path or ""),
                "threads": self._settings.effective_threads,
                "hash_mb": self._settings.stockfish_hash_mb,
                "error": exc.message,
            }

    def llm_health(self) -> Dict[str, object]:
        return {
            "available": self._coach.llm_available,
            "provider": getattr(self._provider, "name", "none"),
            "model": self._settings.deepseek_model if self._coach.llm_available else None,
            "base_url": self._settings.deepseek_base_url if self._coach.llm_available else None,
        }

    def test_llm(self) -> Dict[str, object]:
        """发一次最小的真实请求，验证 Key 到底能不能用。

        /api/health 只能告诉你"配置里有没有 Key"，这里才会真的调一次服务商，
        并把失败原因翻译成可执行的建议。
        """
        if not self._coach.llm_available:
            return {
                "configured": False,
                "ok": False,
                "model": None,
                "message_zh": humanize_error("missing_api_key"),
                "detail": "missing_api_key",
            }

        timeout = min(self._settings.llm_timeout, 30.0)
        probe = build_provider(
            api_key=self._settings.deepseek_api_key,
            base_url=self._settings.deepseek_base_url,
            model=self._settings.deepseek_model,
            timeout=timeout,
            temperature=0.0,
            max_tokens=64,
        )
        result = probe.complete_json(
            system="你是一个连接测试助手，只输出 JSON，不要任何解释。",
            user='请只输出这个 JSON：{"status": "ok"}',
        )
        if result.ok:
            return {
                "configured": True,
                "ok": True,
                "model": result.model or self._settings.deepseek_model,
                "message_zh": "连接正常，AI 解释已启用。打开任意关键局面即可生成中文解释。",
                "detail": None,
            }
        return {
            "configured": True,
            "ok": False,
            "model": self._settings.deepseek_model,
            "message_zh": humanize_error(result.error, timeout),
            "detail": result.error,
        }

    def public_config(self) -> Dict[str, object]:
        """前端可以看的非敏感配置。

        从 service 自己持有的 settings 读，而不是从全局对象读——注入不同配置时
        （测试、或以后多套配置）这里才是一致的那一份。
        """
        return {
            "pass1_depth": self._settings.pass1_depth,
            "pass2_depth": self._settings.pass2_depth,
            "pass2_multipv": self._settings.pass2_multipv,
            "max_critical_moments": self._settings.max_critical_moments,
            "llm_configured": self._settings.llm_enabled,
            "engine_path": str(self._settings.resolved_stockfish_path or ""),
        }

    # -------------------------------------------------------------- analysis

    def start_analysis(
        self,
        pgn: str,
        player_color: Optional[Color] = None,
        max_critical_moments: Optional[int] = None,
        deep: bool = True,
        force: bool = False,
    ) -> StartResult:
        """Parse, then queue the analysis. Raises PgnError for unusable input."""
        with self._db.session() as session:
            known_names = known_player_names(session)

        if count_games(pgn) > 1:
            logger.info("PGN contains multiple games; analyzing the first one")

        parsed = parse_pgn(pgn, player_color=player_color, known_player_names=known_names)
        game_id = make_game_id(pgn, parsed.player_color.value)

        if not force:
            with self._db.session() as session:
                existing = get_review(session, game_id)
            if existing is not None:
                job_id = uuid.uuid4().hex[:12]
                status = AnalysisJobStatus(
                    job_id=job_id,
                    game_id=game_id,
                    status=AnalysisStatus.COMPLETED,
                    progress=1.0,
                    message_zh="该对局已经分析过，直接使用已有结果（未重新运行引擎）。",
                    review=existing,
                )
                self._remember_job(status)
                return StartResult(job_id=job_id, game_id=game_id, status=status)

        job_id = uuid.uuid4().hex[:12]
        limit = max_critical_moments or self._settings.max_critical_moments
        pending = AnalysisJobStatus(
            job_id=job_id,
            game_id=game_id,
            status=AnalysisStatus.PENDING,
            progress=0.0,
            message_zh="已加入队列…",
        )
        self._remember_job(pending)
        with self._db.session() as session:
            upsert_job(session, job_id, AnalysisStatus.PENDING.value, 0.0, "已加入队列…", game_id)

        self._executor.submit(self._run_job, job_id, pgn, parsed, game_id, limit, deep)
        return StartResult(job_id=job_id, game_id=game_id, status=pending)

    def _run_job(self, job_id, pgn, parsed, game_id, limit, deep) -> None:
        self._update_job(job_id, AnalysisStatus.RUNNING, 0.02, "启动引擎…")

        def progress(fraction: float, message: str) -> None:
            self._update_job(
                job_id, AnalysisStatus.RUNNING, max(0.02, min(0.99, fraction)), message
            )

        try:
            engine = self.ensure_engine()
            config = PipelineConfig(
                pass1_depth=self._settings.pass1_depth,
                pass1_nodes=self._settings.pass1_nodes,
                pass2_depth=self._settings.pass2_depth,
                pass2_multipv=self._settings.pass2_multipv,
                pass2_nodes=self._settings.pass2_nodes,
                position_timeout=self._settings.position_timeout,
                max_critical_moments=limit,
                deep=deep,
                threads=self._settings.effective_threads,
                hash_mb=self._settings.stockfish_hash_mb,
            )
            analyzer = GameAnalyzer(
                engine=engine,
                cache=self._analysis_cache,
                config=config,
                progress=progress,
            )
            review = analyzer.analyze(parsed, game_id)
            self._decorate(review)

            with self._db.session() as session:
                save_review(session, review, pgn)

            self._update_job(
                job_id,
                AnalysisStatus.COMPLETED,
                1.0,
                "分析完成：{} 个值得复盘的局面。".format(len(review.critical_moments)),
                review=review,
            )
        except EngineError as exc:
            logger.warning("Analysis job %s failed: %s", job_id, exc.message)
            self._update_job(
                job_id,
                AnalysisStatus.FAILED,
                0.0,
                exc.hint_zh,
                error="{}: {}".format(exc.message, exc.detail or ""),
            )
        except Exception as exc:  # pragma: no cover - unexpected failure
            logger.exception("Unexpected analysis failure in job %s", job_id)
            self._update_job(
                job_id,
                AnalysisStatus.FAILED,
                0.0,
                "分析过程中出现未预期的错误，请重试或降低分析深度。",
                error=str(exc),
            )

    def _decorate(self, review: GameReview) -> None:
        """Fill presentation-only fields that are not part of the analysis itself."""
        for moment in review.critical_moments:
            moment.one_liner_zh = one_liner_zh(moment.evidence)
        review.llm_available = self._coach.llm_available
        review.created_at = review.created_at or datetime.utcnow()

    # ------------------------------------------------------------------- jobs

    def _remember_job(self, status: AnalysisJobStatus) -> None:
        with self._jobs_lock:
            self._jobs[status.job_id] = status

    def _update_job(
        self,
        job_id: str,
        status: AnalysisStatus,
        progress: float,
        message: str,
        error: Optional[str] = None,
        review: Optional[GameReview] = None,
    ) -> None:
        with self._jobs_lock:
            current = self._jobs.get(job_id) or AnalysisJobStatus(
                job_id=job_id, status=status
            )
            current.status = status
            current.progress = round(progress, 4)
            current.message_zh = message
            current.error = error
            if review is not None:
                current.review = review
            self._jobs[job_id] = current
        with self._db.session() as session:
            upsert_job(
                session,
                job_id,
                status.value,
                progress,
                message,
                current.game_id,
                error,
            )

    def job_status(self, job_id: str) -> Optional[AnalysisJobStatus]:
        with self._jobs_lock:
            found = self._jobs.get(job_id)
        if found is not None:
            return found
        with self._db.session() as session:
            row = get_job_row(session, job_id)
            if row is None:
                return None
            return AnalysisJobStatus(
                job_id=row.id,
                game_id=row.game_id,
                status=AnalysisStatus(row.status),
                progress=row.progress or 0.0,
                message_zh=row.message or "",
                error=row.error,
            )

    # ---------------------------------------------------------------- retrieval

    def get_review(self, game_id: str) -> Optional[GameReview]:
        with self._db.session() as session:
            review = get_review(session, game_id)
        if review is not None:
            review.llm_available = self._coach.llm_available
        return review

    def list_games(self, limit: int = 50, offset: int = 0) -> List[GameListItem]:
        with self._db.session() as session:
            return list_games(session, limit=limit, offset=offset)

    def delete_game(self, game_id: str) -> bool:
        with self._db.session() as session:
            return repo_delete_game(session, game_id)

    def explain_moment(self, game_id: str, ply: int) -> Optional[MomentExplanation]:
        review = self.get_review(game_id)
        if review is None:
            return None
        moment = next((item for item in review.critical_moments if item.ply == ply), None)
        if moment is None:
            return None
        return self._coach.explain_moment(moment.evidence)

    def moment_lines(self, game_id: str, ply: int) -> Optional[MomentLinesResponse]:
        """把某一个局面的后续线路展开成可逐步演示的局面序列。

        **任何一手都能查**，不只是关键局面：关键局面用的是第二遍深度分析的线路，
        其余着法用的是第一遍扫描的线路。

        纯 python-chess 重放，不调用引擎、不花钱、毫秒级返回。
        """
        review = self.get_review(game_id)
        if review is None:
            return None
        move = next((item for item in review.moves if item.ply == ply), None)
        if move is None or not move.best_line_uci:
            return None

        # 引擎 PV 保存时截断到固定步数，这里如实告诉前端「线路到此为止」。
        truncated = len(move.best_line_uci) >= PV_STORED_PLIES
        return MomentLinesResponse(
            ply=ply,
            move_number=move.move_number,
            played_move_san=move.san,
            best_move_san=move.best_move_san,
            evaluation_before=move.evaluation_before,
            expected_score_before=move.expected_score_before,
            best=walk_line(
                move.fen_before,
                move.best_line_uci,
                "best",
                "引擎推荐线路",
                pv_limit_reached=truncated,
            ),
            played=walk_line(
                move.fen_before,
                move.played_line_uci,
                "played",
                "实战线路（你实际走出来的）",
                pv_limit_reached=truncated,
            ),
        )

    def game_summary(self, game_id: str) -> Optional[Tuple[GameReview, GameSummaryRecord]]:
        review = self.get_review(game_id)
        if review is None:
            return None
        return review, self._coach.summarize_game(review)

    def profile(self) -> ProfileSummary:
        with self._db.session() as session:
            data = collect_profile_input(session)
        return build_profile(data)


_service: Optional[AnalysisService] = None
_service_lock = threading.Lock()


def get_service() -> AnalysisService:
    global _service
    if _service is None:
        with _service_lock:
            if _service is None:
                _service = AnalysisService()
    return _service


def reset_service() -> None:
    """Test helper: drop the cached service so a fresh database can be used."""
    global _service
    if _service is not None:
        _service.shutdown()
    _service = None


__all__ = ["AnalysisService", "StartResult", "get_service", "reset_service", "probe_engine"]
