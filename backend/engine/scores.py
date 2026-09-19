"""Score normalization and expected-score mathematics.

Single source of truth for turning a UCI ``score cp`` / ``score mate`` / ``wdl``
into the player-perspective numbers used everywhere else.

Why expected score instead of centipawn loss: a 100cp drop at +0.3 and a 100cp drop
at +9.0 are completely different mistakes, while ``expected_score = P(win) +
0.5 * P(draw)`` gives a bounded measure. Stockfish WDL describes engine self-play
under its calibration conditions, not a human player's win probability.
Centipawns are still carried along for display.
"""

import math
from typing import Optional, Tuple

import chess.engine

from models.enums import Color
from models.evidence import WdlDistribution

#: Eval-bar value (pawns) used when the engine reports a forced mate. Kept out of
#: the expected-score maths, which uses WDL, so this sentinel only affects display.
MATE_DISPLAY_PAWNS = 10.0

#: Stockfish reports WDL in permille.
WDL_SCALE = 1000.0

#: Classic Elo expectancy curve, used only when the engine gives no WDL at all.
_CP_EXPECTANCY_DIVISOR = 400.0


def cp_and_mate(pov_score: chess.engine.PovScore, pov: Color) -> Tuple[Optional[int], Optional[int]]:
    """Return (centipawns, mate_in) from ``pov``'s point of view.

    Exactly one of the two is ever non-None: python-chess reports a mate score as a
    ``Mate`` object whose ``.score()`` is None.
    """
    score = pov_score.pov(chess.WHITE if pov is Color.WHITE else chess.BLACK)
    if score.is_mate():
        return None, score.mate()
    return score.score(), None


def display_pawns(cp: Optional[int], mate: Optional[int]) -> Optional[float]:
    """A single number for the UI/graph: pawns, or a signed sentinel for mate."""
    if mate is not None:
        return math.copysign(MATE_DISPLAY_PAWNS, float(mate))
    if cp is None:
        return None
    return round(cp / 100.0, 2)


def expected_score_from_cp(cp: Optional[int], mate: Optional[int]) -> float:
    """Fallback expected score when no WDL is available."""
    if mate is not None:
        return 1.0 if mate > 0 else 0.0
    if cp is None:
        return 0.5
    return 1.0 / (1.0 + math.pow(10.0, -cp / _CP_EXPECTANCY_DIVISOR))


def wdl_from_info(info: chess.engine.InfoDict, pov: Color) -> Tuple[WdlDistribution, bool]:
    """Extract WDL relative to ``pov``.

    Returns ``(wdl, estimated)`` where ``estimated`` is True when the engine line
    carried no WDL and it had to be derived from centipawns. Callers surface that
    flag so severity is never silently presented as WDL-based when it is not.
    """
    pov_wdl = info.get("wdl")
    if pov_wdl is not None:
        wdl = pov_wdl.pov(chess.WHITE if pov is Color.WHITE else chess.BLACK)
        return WdlDistribution.from_permille(wdl.wins, wdl.draws, wdl.losses), False

    score = info.get("score")
    if score is None:
        return WdlDistribution(win=0.5, draw=0.0, loss=0.5), True
    cp, mate = cp_and_mate(score, pov)
    return WdlDistribution.from_expected_score(expected_score_from_cp(cp, mate)), True


def expected_score_loss(before: WdlDistribution, after: WdlDistribution) -> float:
    """How much expected score the played move gave away.

    ``before`` is the position the player was facing (best play available) and
    ``after`` is the position the played move produced (best play by both sides
    from there). A negative raw difference means the played move was actually the
    engine's choice at this search depth, so the loss is clamped to 0.
    """
    return max(0.0, before.expected_score() - after.expected_score())


def centipawn_loss(before_cp: Optional[int], after_cp: Optional[int]) -> Optional[int]:
    """Display-only centipawn delta; None whenever either side is a mate score."""
    if before_cp is None or after_cp is None:
        return None
    return max(0, before_cp - after_cp)


def is_sign_flip(before_es: float, after_es: float, margin: float = 0.10) -> bool:
    """True when the move crosses the 50% boundary (winning side changed)."""
    return (before_es - 0.5) * (after_es - 0.5) < 0 and abs(before_es - after_es) >= margin
