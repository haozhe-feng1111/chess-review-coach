"""Observed human outcomes. These are never engine probabilities."""

from datetime import date, datetime
from typing import List, Literal, Optional

import chess
from pydantic import BaseModel, Field, field_validator, model_validator

RATING_GROUPS = (0, 1000, 1200, 1400, 1600, 1800, 2000, 2200, 2500)
Speed = Literal["ultraBullet", "bullet", "blitz", "rapid", "classical", "correspondence"]


class ExplorerQuery(BaseModel):
    fen: str = Field(min_length=1, max_length=128)
    ratings: List[int] = Field(default_factory=lambda: [1200, 1400, 1600], min_length=1, max_length=9)
    speeds: List[Speed] = Field(default_factory=lambda: ["rapid"], min_length=1, max_length=6)
    since: Optional[str] = None
    until: Optional[str] = None

    @field_validator("fen")
    @classmethod
    def valid_position(cls, value):
        try:
            board = chess.Board(value)
            if not board.is_valid():
                raise ValueError()
        except ValueError:
            raise ValueError("棋盘局面无效，无法查询真人对局。") from None
        return board.fen()

    @field_validator("ratings")
    @classmethod
    def valid_ratings(cls, values):
        if any(value not in RATING_GROUPS for value in values):
            raise ValueError("等级分分组无效。")
        return sorted(set(values))

    @field_validator("speeds")
    @classmethod
    def unique_speeds(cls, values):
        return sorted(set(values))

    @field_validator("since", "until")
    @classmethod
    def valid_month(cls, value):
        if value is not None:
            try:
                if len(value) != 7:
                    raise ValueError()
                date.fromisoformat(value + "-01")
            except ValueError:
                raise ValueError("月份必须是 YYYY-MM。") from None
        return value

    @model_validator(mode="after")
    def date_order(self):
        if self.since and self.until and self.since > self.until:
            raise ValueError("开始月份不能晚于结束月份。")
        return self


class OutcomeCounts(BaseModel):
    white: int = Field(ge=0, strict=True)
    draws: int = Field(ge=0, strict=True)
    black: int = Field(ge=0, strict=True)


class ExplorerMove(OutcomeCounts):
    uci: str
    san: str
    average_rating: Optional[int] = None


class ExplorerData(OutcomeCounts):
    moves: List[ExplorerMove] = Field(default_factory=list)
    opening: Optional[str] = None
    fetched_at: datetime
    source: Literal["lichess_rated_games"] = "lichess_rated_games"


class ExplorerResponse(BaseModel):
    status: Literal["ok", "auth_required", "rate_limited", "unavailable"]
    query: ExplorerQuery
    data: Optional[ExplorerData] = None
    cached: bool = False
    message_zh: str = ""
    retry_after: Optional[int] = None
