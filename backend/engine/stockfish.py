"""Stockfish UCI boundary.

This module is the *only* place that talks to the engine. It owns:

* process lifecycle (start, restart after a crash, shutdown),
* UCI option configuration (Threads, Hash, MultiPV, UCI_ShowWDL),
* score normalization to the analyzed player's point of view,
* turning raw ``info`` dictionaries into the validated :class:`PositionEval` model.

It deliberately contains no chess judgment: it reports what the engine said, in a
typed shape, and nothing else.
"""

import logging
import threading
from concurrent.futures import Future, ThreadPoolExecutor, TimeoutError as FutureTimeout
from dataclasses import dataclass
from pathlib import Path
from time import monotonic
from typing import Any, Dict, List, Optional

import chess
import chess.engine

from engine.errors import (
    EngineCrashedError,
    EngineNotFoundError,
    EngineStartupError,
    EngineTimeoutError,
)
from engine.scores import cp_and_mate, expected_score_from_cp, wdl_from_info
from models.enums import Color
from models.evidence import CandidateMove, PositionEval

logger = logging.getLogger(__name__)

#: How many plies of the principal variation we keep. Deep PVs are large and the
#: explanation only ever needs the first few moves.
PV_MAX_PLIES = 12


@dataclass(frozen=True)
class EngineConfig:
    path: Path
    threads: int = 1
    hash_mb: int = 64
    startup_timeout: float = 20.0


@dataclass(frozen=True)
class EngineIdentity:
    name: str
    path: str


class StockfishEngine:
    """A single Stockfish process, used sequentially.

    Not thread-safe by design: one process serves one analysis job at a time, which
    keeps engine resource usage predictable on a laptop.
    """

    def __init__(self, config: EngineConfig) -> None:
        self._config = config
        self._engine: Optional[chess.engine.SimpleEngine] = None
        self._name: str = "unknown"
        self._lock = threading.RLock()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="stockfish")

    # ------------------------------------------------------------------ lifecycle

    @property
    def name(self) -> str:
        return self._name

    def start(self) -> None:
        with self._lock:
            if self._engine is not None:
                return
            if not self._config.path.exists():
                raise EngineNotFoundError(
                    "Stockfish binary not found", detail=str(self._config.path)
                )
            try:
                self._engine = chess.engine.SimpleEngine.popen_uci(
                    str(self._config.path), timeout=self._config.startup_timeout
                )
            except FileNotFoundError as exc:
                raise EngineNotFoundError("Stockfish binary not found", detail=str(exc)) from exc
            except PermissionError as exc:
                raise EngineStartupError(
                    "Stockfish is not executable", detail=str(exc)
                ) from exc
            except (chess.engine.EngineError, OSError) as exc:
                raise EngineStartupError("Stockfish failed to start", detail=str(exc)) from exc

            self._name = str(self._engine.id.get("name", "Stockfish"))
            self._apply_options()

    def _apply_options(self) -> None:
        assert self._engine is not None
        options: Dict[str, Any] = {
            # WDL is what severity is based on, so it is always requested.
            "UCI_ShowWDL": True,
            "Threads": max(1, self._config.threads),
            "Hash": max(16, self._config.hash_mb),
        }
        available = self._engine.options
        wanted = {key: value for key, value in options.items() if key in available}
        try:
            self._engine.configure(wanted)
        except chess.engine.EngineError as exc:  # pragma: no cover - engine-specific
            logger.warning("Could not configure engine options %s: %s", wanted, exc)
        if "UCI_ShowWDL" not in available:
            logger.warning(
                "Engine does not advertise UCI_ShowWDL (%s); "
                "expected scores will be estimated from centipawns.",
                self._name,
            )

    def close(self) -> None:
        with self._lock:
            if self._engine is not None:
                try:
                    self._engine.quit()
                except Exception:  # pragma: no cover - best effort shutdown
                    logger.debug("Engine did not shut down cleanly", exc_info=True)
                self._engine = None
            self._executor.shutdown(wait=False)

    def restart(self) -> None:
        """Recover from a crash or a timeout by replacing the process."""
        logger.warning("Restarting Stockfish after a failure")
        with self._lock:
            if self._engine is not None:
                try:
                    self._engine.quit()
                except Exception:  # pragma: no cover
                    pass
                self._engine = None
        self.start()

    def __enter__(self) -> "StockfishEngine":
        self.start()
        return self

    def __exit__(self, *_exc_info: object) -> None:
        self.close()

    # ------------------------------------------------------------------- analysis

    def analyse(
        self,
        board: chess.Board,
        pov_color: Color,
        depth: int = 12,
        nodes: int = 0,
        multipv: int = 1,
        timeout: Optional[float] = None,
        root_moves: Optional[List[str]] = None,
    ) -> PositionEval:
        """Search ``board`` and normalize the result to ``pov_color``'s view.

        ``root_moves`` restricts the search to the given UCI moves. That is how the app
        grades a move a human actually played ("what does the engine think of *this*
        move?") without pretending it was the engine's own choice.
        """
        fen = board.fen()
        if board.is_game_over(claim_draw=False):
            # Checkmate/stalemate has no principal variation by definition. Reporting it
            # as an empty result lets callers derive the terminal WDL themselves.
            return PositionEval(
                fen=fen,
                pov_color=pov_color,
                depth=0,
                multipv=0,
                engine_name=self._name,
                candidates=[],
                complete=True,
                warnings=["terminal position: no engine search performed"],
            )

        restricted: Optional[List[chess.Move]] = None
        if root_moves:
            restricted = []
            for uci in root_moves:
                try:
                    move = chess.Move.from_uci(uci)
                except ValueError as exc:
                    raise ValueError("不是合法的 UCI 着法：{}".format(uci)) from exc
                if move not in board.legal_moves:
                    raise ValueError("{} 在当前位置不合法".format(uci))
                restricted.append(move)

        with self._lock:
            self.start()

        limit = chess.engine.Limit(nodes=nodes) if nodes > 0 else chess.engine.Limit(depth=depth)
        started = monotonic()
        # 限制到具体着法时 MultiPV 没有意义：只有一个根着法可以选
        multi = 1 if restricted else max(1, multipv)

        def run() -> List[chess.engine.InfoDict]:
            assert self._engine is not None
            result = self._engine.analyse(
                board, limit, multipv=multi, root_moves=restricted
            )
            # SimpleEngine returns a single dict for MultiPV=1 and a list otherwise.
            if isinstance(result, dict):
                return [result]
            return list(result)

        try:
            infos = self._run_with_timeout(run, timeout)
        except EngineTimeoutError:
            self.restart()
            raise
        except chess.engine.EngineTerminatedError as exc:
            self.restart()
            raise EngineCrashedError("Stockfish terminated unexpectedly", detail=str(exc)) from exc
        except (chess.engine.EngineError, BrokenPipeError, OSError) as exc:
            self.restart()
            raise EngineCrashedError("Stockfish communication failed", detail=str(exc)) from exc

        elapsed = monotonic() - started
        candidates: List[CandidateMove] = []
        warnings: List[str] = []
        max_depth = 0
        total_nodes: Optional[int] = None

        for info in infos:
            candidate = self._build_candidate(board, info, pov_color)
            if candidate is None:
                continue
            candidates.append(candidate)
            max_depth = max(max_depth, int(info.get("depth", 0) or 0))
            if info.get("nodes") is not None:
                total_nodes = int(info["nodes"])

        if not candidates:
            raise EngineCrashedError("Stockfish returned no usable principal variation")

        if any(self._wdl_missing(info) for info in infos):
            warnings.append(
                "Engine line carried no WDL; expected score was estimated from centipawns."
            )

        return PositionEval(
            fen=fen,
            pov_color=pov_color,
            depth=max_depth,
            multipv=len(candidates),
            engine_name=self._name,
            nodes=total_nodes,
            time_s=round(elapsed, 3),
            candidates=candidates,
            complete=True,
            warnings=warnings,
        )

    def _run_with_timeout(self, fn: Any, timeout: Optional[float]) -> List[chess.engine.InfoDict]:
        if not timeout or timeout <= 0:
            return fn()
        future: Future = self._executor.submit(fn)
        try:
            return future.result(timeout=timeout)
        except FutureTimeout as exc:
            future.cancel()
            raise EngineTimeoutError(
                "Engine search exceeded the configured per-position time limit",
                detail="timeout={}s".format(timeout),
            ) from exc

    @staticmethod
    def _wdl_missing(info: chess.engine.InfoDict) -> bool:
        return info.get("wdl") is None

    def _build_candidate(
        self, board: chess.Board, info: chess.engine.InfoDict, pov_color: Color
    ) -> Optional[CandidateMove]:
        score = info.get("score")
        pv = info.get("pv") or []
        if score is None or not pv:
            return None

        cp, mate = cp_and_mate(score, pov_color)
        wdl, _estimated = wdl_from_info(info, pov_color)
        pv_moves = list(pv[:PV_MAX_PLIES])
        pv_san = self._san_list(board, pv_moves)

        return CandidateMove(
            uci=pv_moves[0].uci(),
            san=pv_san[0] if pv_san else pv_moves[0].uci(),
            cp=cp,
            mate=mate,
            wdl=wdl,
            expected_score=round(
                wdl.expected_score()
                if info.get("wdl") is not None
                else expected_score_from_cp(cp, mate),
                6,
            ),
            pv_uci=[move.uci() for move in pv_moves],
            pv_san=pv_san,
        )

    # ---------------------------------------------------------------------- misc

    @staticmethod
    def _san_list(board: chess.Board, moves: List[chess.Move]) -> List[str]:
        """SAN for a principal variation, truncated at the first unusable move.

        ``board.variation_san`` returns one formatted string; the UI and the detectors
        both want a per-ply list, so it is built by replaying the line on a copy.
        """
        replay = board.copy(stack=False)
        sans: List[str] = []
        for move in moves:
            try:
                sans.append(replay.san(move))
                replay.push(move)
            except (ValueError, AssertionError):  # pragma: no cover - defensive
                break
        return sans

def probe_engine(config: EngineConfig) -> EngineIdentity:
    """Start the engine once, read its identity, shut it down (used by /health)."""
    engine = StockfishEngine(config)
    try:
        engine.start()
        return EngineIdentity(name=engine.name, path=str(config.path))
    finally:
        engine.close()
