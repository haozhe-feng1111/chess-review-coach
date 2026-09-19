"""One interruptible UCI worker for the local analysis board.

The latest position replaces the previous search. Polling renews a short lease, so
closing a browser also stops an infinite search. Batch review uses its own engine.
"""

import copy
import os
import threading
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Optional

import chess
import chess.engine
import psutil

from models.workbench import SearchSettings, StartSearch


def resource_limits() -> dict:
    return {
        "max_threads": min(64, os.cpu_count() or 1),
        "max_hash_mb": max(16, min(4096, int(psutil.virtual_memory().total / (1024**2) / 4))),
        "max_depth": 60,
        "max_seconds": 600,
    }


def search_board(request: StartSearch) -> chess.Board:
    board = chess.Board(request.root_fen)
    if not board.is_valid():
        raise ValueError("局面无效，无法分析。")
    for uci in request.moves:
        move = chess.Move.from_uci(uci)
        if move not in board.legal_moves:
            raise ValueError("分析线路中存在非法走法。")
        board.push(move)
    return board


@dataclass
class SearchJob:
    request: StartSearch
    board: chess.Board
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    cancel: threading.Event = field(default_factory=threading.Event)
    touched: float = field(default_factory=time.monotonic)
    snapshot: dict = field(default_factory=dict)


class LiveAnalysis:
    def __init__(self, path, *, lease_seconds=15.0, engine_factory=None):
        self.path = path
        self.lease_seconds = lease_seconds
        self.factory = engine_factory or chess.engine.SimpleEngine.popen_uci
        self.condition = threading.Condition()
        self.jobs = OrderedDict()
        self.sequences = OrderedDict()
        self.pending: Optional[SearchJob] = None
        self.active: Optional[SearchJob] = None
        self.closed = False
        self.engine = None
        self.worker = threading.Thread(target=self._run, name="live-stockfish", daemon=True)
        self.worker.start()

    def start(self, request: StartSearch) -> dict:
        board = search_board(request)
        limits = resource_limits()
        if request.settings.threads > limits["max_threads"] or request.settings.hash_mb > limits["max_hash_mb"]:
            raise ValueError("资源设置超过这台电脑允许的范围。")
        job = SearchJob(request, board)
        job.snapshot = {
            "id": job.id, "fen": board.fen(), "status": "queued", "engine": "Stockfish",
            "settings": request.settings.model_dump(), "applied": False,
            "depth": 0, "nodes": 0, "nps": 0, "elapsed": 0.0, "hashfull": 0,
            "memory_mb": None, "lines": [], "error": None, "outcome": None,
        }
        with self.condition:
            if self.closed:
                raise RuntimeError("引擎已关闭。")
            if request.sequence <= self.sequences.get(request.client_id, 0):
                raise ValueError("这个局面的请求已被更新的局面替代。")
            self.sequences[request.client_id] = request.sequence
            self.sequences.move_to_end(request.client_id)
            while len(self.sequences) > 128:
                self.sequences.popitem(last=False)
            if self.active:
                self.active.cancel.set()
            if self.pending:
                self.pending.cancel.set()
                self.pending.snapshot["status"] = "stopped"
            self.pending = job
            self.jobs[job.id] = job
            while len(self.jobs) > 32:
                self.jobs.popitem(last=False)
            self.condition.notify_all()
            return copy.deepcopy(job.snapshot)

    def read(self, job_id: str) -> Optional[dict]:
        with self.condition:
            job = self.jobs.get(job_id)
            if not job:
                return None
            job.touched = time.monotonic()
            return copy.deepcopy(job.snapshot)

    def stop(self, job_id: str) -> bool:
        with self.condition:
            job = self.jobs.get(job_id)
            if not job:
                return False
            job.cancel.set()
            return True

    def close(self):
        with self.condition:
            self.closed = True
            if self.active:
                self.active.cancel.set()
            if self.pending:
                self.pending.cancel.set()
            self.condition.notify_all()
        self.worker.join(timeout=5)
        if self.worker.is_alive() and self.engine:
            self.engine.close()
            self.worker.join(timeout=2)

    def _publish(self, job, **values):
        with self.condition:
            job.snapshot.update(values)

    def _run(self):
        try:
            while True:
                with self.condition:
                    self.condition.wait_for(lambda: self.closed or self.pending is not None)
                    if self.closed:
                        return
                    job, self.pending = self.pending, None
                    self.active = job
                try:
                    self._search(job)
                except Exception:
                    self._publish(job, status="failed", error="引擎分析中断，请重试或降低资源设置。")
                    if self.engine:
                        self.engine.close()
                        self.engine = None
                finally:
                    with self.condition:
                        self.active = None
        finally:
            if self.engine:
                self.engine.close()
                self.engine = None

    def _search(self, job: SearchJob):
        if job.cancel.is_set():
            self._publish(job, status="stopped")
            return
        outcome = job.board.outcome(claim_draw=False)
        if outcome:
            self._publish(job, status="completed", outcome={
                "result": outcome.result(), "reason": outcome.termination.name.lower(),
            })
            return
        if self.engine is None:
            self.engine = self.factory(str(self.path), timeout=10)
        config = job.request.settings
        self.engine.configure({"Threads": config.threads, "Hash": config.hash_mb})
        self.engine.ping()
        self._publish(job, engine=self.engine.id.get("name", "Stockfish"), applied=True, status="running")
        limit = (chess.engine.Limit(time=config.seconds) if config.mode == "time" else
                 chess.engine.Limit(depth=config.depth) if config.mode == "depth" else None)
        started = time.monotonic()
        result = self.engine.analysis(job.board, limit, multipv=config.multipv, game=job.request.client_id)
        stopped_at = None
        next_publish = 0.0
        infos = {}
        process = psutil.Process(self.engine.transport.get_pid())
        try:
            while True:
                now = time.monotonic()
                expired = now - job.touched > self.lease_seconds
                if (job.cancel.is_set() or expired or self.closed) and stopped_at is None:
                    result.stop()
                    stopped_at = now
                if stopped_at is not None and now - stopped_at > 3:
                    raise TimeoutError("UCI stop timeout")
                finished = False
                # Drain a bounded batch before checking cancellation again.
                for _ in range(64):
                    if result.would_block():
                        break
                    info = result.next()
                    if info is None:
                        finished = True
                        break
                    if "pv" in info and "score" in info:
                        infos[info.get("multipv", 1)] = info
                if now >= next_publish or finished:
                    lines = []
                    for rank, info in sorted(infos.items()):
                        cursor = job.board.copy()
                        ucis, sans = [], []
                        for move in info.get("pv", [])[:32]:
                            if move not in cursor.legal_moves:
                                break
                            sans.append(cursor.san(move))
                            ucis.append(move.uci())
                            cursor.push(move)
                        if not ucis:
                            continue
                        score = info["score"].white()
                        lines.append({"rank": rank, "depth": info.get("depth", 0),
                                      "cp": score.score(), "mate": score.mate(),
                                      "bound": ("lower" if job.board.turn else "upper") if info.get("lowerbound") else
                                               ("upper" if job.board.turn else "lower") if info.get("upperbound") else None,
                                      "pv_uci": ucis, "pv_san": sans})
                    latest = max(infos.values(), key=lambda i: i.get("nodes", 0), default={})
                    try:
                        memory = round(process.memory_info().rss / 1024**2, 1)
                    except psutil.Error:
                        memory = None
                    self._publish(job, lines=lines, depth=max((i.get("depth", 0) for i in infos.values()), default=0),
                                  nodes=latest.get("nodes", 0), nps=latest.get("nps", 0),
                                  hashfull=latest.get("hashfull", 0), memory_mb=memory,
                                  elapsed=round(now-started, 2))
                    next_publish = now + 0.12
                if finished:
                    self._publish(job, status="stopped" if stopped_at is not None else "completed")
                    return
                time.sleep(0.015)
        finally:
            result.stop()
