"""Chess-judgment thresholds, in one place.

These numbers decide when a move is called an inaccuracy or a blunder and which
positions deserve deep analysis. They are **engineering defaults, not science**:
the exact boundaries between "inaccuracy" and "mistake" are a product decision,
and the widely used values (Lichess/Chess.com-style win-probability deltas) are
only loosely calibrated against human play. Treat every constant here as tunable.

Severity is driven by *expected-score loss* (win + 0.5 * draw, taken from the
engine's WDL model) rather than raw centipawn loss, because a 100cp swing means
something very different at +0.2 than at +9.0.
"""

from dataclasses import dataclass
from typing import Dict, Optional

from models.enums import Severity


@dataclass(frozen=True)
class SeverityThresholds:
    """Expected-score-loss buckets, from the analyzed player's point of view.

    Bucket boundaries are the *upper* bound of each bucket; anything above
    ``mistake_max`` is a blunder.
    """

    # A move within this margin of the engine's own choice still counts as "best".
    best_move_epsilon: float = 0.005
    excellent_max: float = 0.02
    good_max: float = 0.05
    inaccuracy_max: float = 0.10
    mistake_max: float = 0.20

    def classify(self, score_loss: float, is_engine_best: bool) -> Severity:
        loss = max(0.0, score_loss)
        if is_engine_best or loss <= self.best_move_epsilon:
            return Severity.BEST
        if loss <= self.excellent_max:
            return Severity.EXCELLENT
        if loss <= self.good_max:
            return Severity.GOOD
        if loss <= self.inaccuracy_max:
            return Severity.INACCURACY
        if loss <= self.mistake_max:
            return Severity.MISTAKE
        return Severity.BLUNDER


@dataclass(frozen=True)
class CriticalityWeights:
    """Weights used to rank candidate critical positions.

    Expected-score loss dominates; the other signals promote positions that are
    pedagogically important but may have a modest numeric swing (a missed forced
    mate, a sign flip, a unique-only-move position).
    """

    expected_score_loss: float = 1.0
    sign_flip: float = 0.30
    missed_win: float = 0.35
    mate_appears: float = 0.40
    mate_disappears: float = 0.30
    position_collapse: float = 0.25  # winning/drawn -> losing
    forced_sequence: float = 0.10
    best_move_uniqueness: float = 0.15


@dataclass(frozen=True)
class PhaseThresholds:
    """Heuristic opening/middlegame/endgame classification.

    Opening: by full move number OR while most minor pieces are still at home.
    Endgame: little non-pawn material left on the board.
    Everything else is the middlegame. Isolated here so it can be replaced by a
    better model later without touching analysis code.
    """

    opening_max_fullmove: int = 10
    # Non-pawn, non-king material value still on the board at or below which the
    # position counts as an endgame (queens=9, rooks=5, minors=3).
    endgame_material_threshold: int = 13
    # In the opening, if this many minor pieces are still on their home squares the
    # position is treated as opening regardless of move number.
    undeveloped_minor_threshold: int = 3


@dataclass(frozen=True)
class DetectionThresholds:
    """Confidence floors and material cutoffs used by concept detectors."""

    # Material (in pawns) that must be at stake before we call something a real loss.
    significant_material_loss: float = 1.0
    # Minimum value of a piece for it to count as a fork/skewer target.
    minor_piece_value: int = 3
    # A move must beat the runner-up by at least this much expected score before we
    # call the best move "unique".
    uniqueness_margin: float = 0.10
    # An expected score this high means the player was clearly winning.
    winning_expected_score: float = 0.85
    # Below this expected score the player is clearly worse / lost.
    losing_expected_score: float = 0.35
    # Trapped piece: attacked, mobile but with at most this many safe squares.
    trapped_piece_max_safe_squares: int = 1


@dataclass(frozen=True)
class TimePressureThresholds:
    """什么时候算"时间紧张"。

    两个条件取较宽的那个：剩余时间少于本局基本用时的 10%，或者少于 20 秒。
    "10%" 对不同时限都成立（5 分钟棋的 30 秒、15 分钟棋的 90 秒），
    20 秒的下限是为了别在超快棋里把每一步都算成时间紧张。
    这是工程默认值，不是标定过的结论——所以界面上永远同时给出**实际剩余秒数**，
    让使用者自己判断这个标签合不合理。
    """

    fraction_of_base: float = 0.10
    floor_seconds: float = 20.0

    def limit_for(self, base_seconds: Optional[int]) -> float:
        base = float(base_seconds or 0)
        return max(self.floor_seconds, self.fraction_of_base * base)


@dataclass(frozen=True)
class AnalysisThresholds:
    severity: SeverityThresholds = SeverityThresholds()
    criticality: CriticalityWeights = CriticalityWeights()
    phase: PhaseThresholds = PhaseThresholds()
    detection: DetectionThresholds = DetectionThresholds()
    time_pressure: TimePressureThresholds = TimePressureThresholds()
    # Minimum number of games before profile statistics claim a recurring pattern.
    profile_recurring_min_games: int = 3
    profile_recurring_min_events: int = 5


THRESHOLDS = AnalysisThresholds()

SEVERITY_LABELS_ZH: Dict[Severity, str] = {
    Severity.BEST: "最佳",
    Severity.EXCELLENT: "优秀",
    Severity.GOOD: "良好",
    Severity.INACCURACY: "不够精确",
    Severity.MISTAKE: "失误",
    Severity.BLUNDER: "严重失误",
}
