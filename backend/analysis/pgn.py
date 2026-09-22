"""PGN parsing.

Parsing is strict on purpose: a game that python-chess could only partly read would
otherwise produce a review of a game the user never played. Any parse error is
surfaced as a :class:`PgnError` with the underlying reason.
"""

import io
import re
from typing import List, Optional, Sequence

import chess
import chess.pgn

from engine.errors import PgnError
from models.enums import Color
from models.game import ParsedGame, ParsedMove

MAX_PLIES = 400  # a very long game; anything beyond this is almost certainly junk

#: ``[%clk 0:04:31]`` / ``[%clk 0:02:59.9]`` / ``[%clk 1:30:00]``
CLOCK_PATTERN = re.compile(r"\[%clk\s+(\d+):(\d{1,2}):(\d{1,2}(?:\.\d+)?)\]")


def parse_clock_comment(comment: Optional[str]) -> Optional[float]:
    """Seconds remaining from a PGN clock comment; ``None`` when there is no clock.

    Lichess and chess.com both write the time **left after the move** as
    ``[%clk H:MM:SS]``. The value is taken literally — this is the only trustworthy
    source of "how much time was on the clock", and its absence is reported as
    unknown rather than estimated.
    """
    if not comment:
        return None
    match = CLOCK_PATTERN.search(comment)
    if match is None:
        return None
    hours, minutes, seconds = match.groups()
    total = int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    return round(total, 3)



def _read_game(pgn_text: str) -> chess.pgn.Game:
    text = pgn_text.lstrip("\ufeff").strip()
    if not text:
        raise PgnError("PGN text is empty", detail="empty input")

    stream = io.StringIO(text)
    try:
        game = chess.pgn.read_game(stream)
    except (ValueError, IndexError, KeyError) as exc:
        raise PgnError("PGN could not be parsed", detail=str(exc)) from exc

    if game is None:
        raise PgnError("No chess game found in the PGN text", detail="read_game returned None")

    if game.errors:
        first = game.errors[0]
        raise PgnError(
            "PGN contains errors and would be analyzed only partially",
            detail="{}: {}".format(type(first).__name__, first),
        )
    return game


def count_games(pgn_text: str) -> int:
    """How many games the text contains (the API analyzes the first one)."""
    stream = io.StringIO(pgn_text.lstrip("\ufeff"))
    count = 0
    while True:
        game = chess.pgn.read_game(stream)
        if game is None:
            return count
        count += 1
        if count > 50:  # enough to tell the user "multiple games"
            return count


def detect_player_color(
    headers: dict, known_player_names: Optional[Sequence[str]] = None
) -> Optional[Color]:
    """Guess which side the user played by matching names seen in earlier games.

    Returns None when there is no confident answer — the caller then asks the user
    instead of silently assuming a side.
    """
    if not known_player_names:
        return None
    known = {name.strip().lower() for name in known_player_names if name and name.strip()}
    if not known:
        return None

    white = str(headers.get("White", "")).strip().lower()
    black = str(headers.get("Black", "")).strip().lower()
    white_match = white in known if white else False
    black_match = black in known if black else False
    if white_match and not black_match:
        return Color.WHITE
    if black_match and not white_match:
        return Color.BLACK
    return None


def parse_pgn(
    pgn_text: str,
    player_color: Optional[Color] = None,
    known_player_names: Optional[Sequence[str]] = None,
) -> ParsedGame:
    """Parse one PGN into a :class:`ParsedGame` with per-ply FENs.

    ``player_color`` wins if given; otherwise the known-player-name heuristic is
    tried; otherwise White is assumed and ``player_color_source`` says so, so the UI
    can ask the user to confirm.
    """
    game = _read_game(pgn_text)
    headers = {str(key): str(value) for key, value in game.headers.items()}

    warnings: List[str] = []
    if player_color is not None:
        resolved_color = player_color
        source = "explicit"
    else:
        detected = detect_player_color(headers, known_player_names)
        if detected is not None:
            resolved_color = detected
            source = "detected"
        else:
            resolved_color = Color.WHITE
            source = "default"
            warnings.append("无法自动判断你执哪一方，已默认按白方分析，请在页面上确认。")

    board = game.board()
    initial_fen = board.fen()
    moves: List[ParsedMove] = []

    node = game
    for index, move in enumerate(game.mainline_moves(), start=1):
        node = node.variation(0) if node.variations else node
        clock = parse_clock_comment(node.comment) if node is not None else None
        if index > MAX_PLIES:
            warnings.append("棋局超过 {} 步，仅分析前 {} 步。".format(MAX_PLIES, MAX_PLIES))
            break
        if move not in board.legal_moves:
            raise PgnError(
                "PGN contains an illegal move",
                detail="ply {} ({})".format(index, move.uci()),
            )
        fen_before = board.fen()
        try:
            san = board.san(move)
        except (ValueError, AssertionError) as exc:  # pragma: no cover - defensive
            raise PgnError("PGN contains an unreadable move", detail=str(exc)) from exc
        board.push(move)
        moves.append(
            ParsedMove(
                ply=index,
                move_number=(index + 1) // 2,
                color=Color.WHITE if index % 2 == 1 else Color.BLACK,
                san=san,
                uci=move.uci(),
                fen_before=fen_before,
                fen_after=board.fen(),
                clock_seconds=clock,
            )
        )

    if not moves:
        raise PgnError("PGN contains no moves", detail="mainline is empty")

    from analysis.openings import identify_opening
    from analysis.timecontrol import parse_time_control

    opening = headers.get("Opening") or identify_opening([move.san for move in moves])

    return ParsedGame(
        headers=headers,
        moves=moves,
        player_color=resolved_color,
        player_color_source=source,
        white=headers.get("White", "White"),
        black=headers.get("Black", "Black"),
        result=headers.get("Result", "*"),
        initial_fen=initial_fen,
        opening=opening,
        time_control=parse_time_control(headers),
        warnings=warnings,
    )
