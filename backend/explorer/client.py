"""Authenticated, cached Lichess explorer. One upstream request at a time."""

import hashlib
import json
import math
import threading
import time
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import chess
import httpx
from sqlalchemy import delete

from explorer.auth import LichessAuth
from models.explorer import ExplorerData, ExplorerMove, ExplorerQuery, ExplorerResponse, OutcomeCounts
from storage.db import Database
from storage.models import ExplorerCacheEntry

EXPLORER_URL = "https://explorer.lichess.org/lichess"
CACHE_TTL = timedelta(hours=24)


def cache_key(query: ExplorerQuery) -> str:
    values = query.model_dump()
    # Halfmove/fullmove counters do not change the historical position statistics.
    values["fen"] = " ".join(query.fen.split()[:4])
    return hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()


class LichessExplorer:
    def __init__(self, database: Database, account: LichessAuth, timeout: float = 12, transport=None):
        self.db = database
        self.account = account
        self.timeout = timeout
        self.transport = transport
        self._lock = threading.Lock()
        self._blocked_until = 0.0

    def _cached(self, key):
        with self.db.session() as session:
            row = session.get(ExplorerCacheEntry, key)
            if row and row.fetched_at > datetime.now(timezone.utc).replace(tzinfo=None) - CACHE_TTL:
                try:
                    return ExplorerData.model_validate(row.payload)
                except ValueError:
                    session.delete(row)
        return None

    def query(self, query: ExplorerQuery) -> ExplorerResponse:
        key = cache_key(query)
        # Recheck the cache inside the lock so simultaneous identical requests coalesce.
        with self._lock:
            cached = self._cached(key)
            if cached is not None:
                return ExplorerResponse(status="ok", query=query, data=cached, cached=True)
            token = self.account.token()
            if not token:
                return ExplorerResponse(status="auth_required", query=query, message_zh="连接 Lichess 后可查看真人对局统计。")
            remaining = math.ceil(self._blocked_until - time.monotonic())
            if remaining > 0:
                return ExplorerResponse(status="rate_limited", query=query, retry_after=remaining,
                                        message_zh="Lichess 请求较多，请稍后点击刷新。")
            params = dict(variant="standard", fen=query.fen, ratings=",".join(map(str, query.ratings)),
                          speeds=",".join(query.speeds), moves=12, topGames=0, recentGames=0)
            if query.since:
                params["since"] = query.since
            if query.until:
                params["until"] = query.until
            try:
                with httpx.Client(timeout=self.timeout, transport=self.transport, follow_redirects=False) as client:
                    response = client.get(EXPLORER_URL, params=params, headers={
                        "Authorization": "Bearer " + token,
                        "Accept": "application/json", "User-Agent": "chess-review-coach/0.1",
                    })
                if response.status_code in (401, 403):
                    return ExplorerResponse(status="auth_required", query=query,
                                            message_zh="Lichess 未接受当前授权，请重新连接。")
                if response.status_code == 429:
                    delay = retry_delay(response.headers.get("Retry-After"))
                    self._blocked_until = time.monotonic() + delay
                    return ExplorerResponse(status="rate_limited", query=query, retry_after=delay,
                                            message_zh="Lichess 暂时限流，请等待后再刷新。")
                response.raise_for_status()
                data = self._parse(response.json(), query)
            except (httpx.HTTPError, ValueError, TypeError, KeyError):
                return ExplorerResponse(status="unavailable", query=query,
                                        message_zh="暂时无法获取 Lichess 数据，请检查网络后刷新；引擎复盘仍可使用。")
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            with self.db.session() as session:
                session.merge(ExplorerCacheEntry(cache_key=key, fetched_at=now, payload=data.model_dump(mode="json")))
                session.execute(delete(ExplorerCacheEntry).where(ExplorerCacheEntry.fetched_at < now - CACHE_TTL))
            return ExplorerResponse(status="ok", query=query, data=data)

    @staticmethod
    def _parse(payload, query):
        counts = OutcomeCounts.model_validate(payload)
        board = chess.Board(query.fen)
        moves = []
        seen = set()
        items = payload["moves"]
        if not isinstance(items, list) or len(items) > 12:
            raise ValueError("invalid explorer moves")
        for item in items:
            if not isinstance(item, dict):
                raise ValueError("invalid explorer move")
            move = chess.Move.from_uci(item["uci"])
            if move not in board.legal_moves or move.uci() in seen:
                raise ValueError("invalid explorer move")
            seen.add(move.uci())
            moves.append(ExplorerMove(
                **OutcomeCounts.model_validate(item).model_dump(), uci=move.uci(), san=board.san(move),
                average_rating=item.get("averageRating"),
            ))
        for outcome in ("white", "draws", "black"):
            if sum(getattr(move, outcome) for move in moves) > getattr(counts, outcome):
                raise ValueError("inconsistent explorer totals")
        opening = payload.get("opening")
        return ExplorerData(**counts.model_dump(), moves=moves, fetched_at=datetime.now(timezone.utc),
                            opening=opening.get("name") if isinstance(opening, dict) else None)


def retry_delay(value):
    try:
        seconds = int(value)
    except (ValueError, TypeError):
        try:
            seconds = math.ceil((parsedate_to_datetime(value) - datetime.now(timezone.utc)).total_seconds())
        except (ValueError, TypeError, OverflowError):
            seconds = 60
    return max(60, min(seconds, 3600))
