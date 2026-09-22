"""PGN-derived game models."""

from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from models.enums import Color


class TimeControl(BaseModel):
    """本局的时间设置，直接来自 PGN 头，不做猜测。

    ``estimated_seconds`` 是按"40 回合"估的整局时长（Lichess 的口径），只用来分档；
    真正有据可查的是 ``base_seconds`` 和 ``increment_seconds``。
    """

    base_seconds: int
    increment_seconds: int = 0
    estimated_seconds: int = 0
    #: ultrabullet / bullet / blitz / rapid / classical
    speed: str = "unknown"
    speed_label_zh: str = "未知时限"
    readable_zh: str = ""


class ParsedMove(BaseModel):
    """One half-move straight from the PGN, with the FENs needed to render it."""

    ply: int  # 1-based: ply 1 is White's first move
    move_number: int
    color: Color
    san: str
    uci: str
    fen_before: str
    fen_after: str
    #: 走完这一手之后剩余的时间（秒）。PGN 带 ``[%clk ...]`` 注释时才有；
    #: 没有就是 None——宁可留空，也不按"大概还剩多少"去编。
    clock_seconds: Optional[float] = None


class ParsedGame(BaseModel):
    headers: Dict[str, str] = Field(default_factory=dict)
    moves: List[ParsedMove] = Field(default_factory=list)
    player_color: Color = Color.WHITE
    #: "explicit" (user chose), "detected" (matched a known player name), or
    #: "default" (nobody knew — the UI must ask the user to confirm).
    player_color_source: str = "explicit"
    white: str = "White"
    black: str = "Black"
    result: str = "*"
    initial_fen: str = ""
    opening: Optional[str] = None
    time_control: Optional[TimeControl] = None
    warnings: List[str] = Field(default_factory=list)

    @property
    def has_clocks(self) -> bool:
        """这盘棋的 PGN 是否带逐手时钟（至少有一手）。

        不做成"每一手都有"：手工整理或截断过的 PGN 可能只注释了一部分，
        那种情况下"部分有数据"也要能用——覆盖率由 TimePressureSummary 如实报出来。
        """
        return any(move.clock_seconds is not None for move in self.moves)

    @property
    def full_moves(self) -> int:
        return (len(self.moves) + 1) // 2

    def player_moves(self) -> List[ParsedMove]:
        return [move for move in self.moves if move.color is self.player_color]
