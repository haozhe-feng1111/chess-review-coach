"""Time-control parsing and bucketing.

A PGN header carries the time control (``[TimeControl "300+3"]``) even when the moves
carry no clock comments, so this gives every analyzed game *some* time information.
The bucket boundaries follow Lichess' published "speed" rule, because that is the
convention players already have in their heads:

    estimated duration = base seconds + 40 * increment seconds
    bullet    < 180       blitz 180-479      rapid 480-1499     classical >= 1500

The 40-move assumption is Lichess' own estimate (also used by ``lichess-puzzler``), not
a measurement of the game, so every user-facing string says "约" and the raw base and
increment are reported alongside the bucket.
"""

from typing import Dict, Optional, Tuple

from models.game import TimeControl

#: Lichess' estimate of a game's length, used for the bucket boundaries.
ESTIMATED_MOVES = 40

#: (upper bound in seconds, value, 中文标签) — the first bucket that fits wins.
SPEED_BUCKETS: Tuple[Tuple[float, str, str], ...] = (
    (30, "ultrabullet", "极速（约 30 秒以内）"),
    (180, "bullet", "子弹（约 3 分钟以内）"),
    (480, "blitz", "超快棋（约 3–8 分钟）"),
    (1500, "rapid", "快棋（约 8–25 分钟）"),
    (float("inf"), "classical", "慢棋（约 25 分钟以上）"),
)

#: 分档的短标签，用于档案页这类需要紧凑显示的地方。
SPEED_LABELS_ZH: Dict[str, str] = {
    "ultrabullet": "极速",
    "bullet": "子弹",
    "blitz": "超快棋",
    "rapid": "快棋",
    "classical": "慢棋",
    "unknown": "未知时限",
}


def speed_label_zh(speed: Optional[str]) -> str:
    return SPEED_LABELS_ZH.get(str(speed or "unknown"), "未知时限")


#: 只有"每步都带时钟"的对局才能做逐手的时间压力判断。
CLOCK_COMMENT_PREFIXES = ("%clk", "%emt")


def parse_time_control(headers: dict) -> Optional[TimeControl]:
    """Parse the ``TimeControl`` header; ``None`` when absent or unparseable.

    Handles ``"300"``, ``"300+3"``, ``"40/7200:1800+30"`` (FIDE-style), ``"-"``
    (correspondence) and chess.com's ``"1/259200"`` (correspondence in days).
    Anything that is not a plain seconds[+increment] form is reported as unknown
    rather than guessed.
    """
    raw = str(headers.get("TimeControl", "") or "").strip()
    if not raw or raw == "-":
        return None
    # FIDE 写法 "40/7200:1800+30"：真正的时限是冒号后面的部分
    if ":" in raw:
        raw = raw.split(":", 1)[1]
    # 通讯棋："1/259200"（每步若干天）——单位不是秒，直接如实标为未知
    if "/" in raw:
        return None
    base_part, _, increment_part = raw.partition("+")
    try:
        base = float(base_part)
        increment = float(increment_part) if increment_part else 0.0
    except ValueError:
        return None
    if base <= 0:
        return None
    return _build(base, increment)


def _build(base: float, increment: float) -> TimeControl:
    estimated = base + ESTIMATED_MOVES * increment
    speed, label = SPEED_BUCKETS[-1][1], SPEED_BUCKETS[-1][2]
    for upper, value, text in SPEED_BUCKETS:
        if estimated < upper:
            speed, label = value, text
            break
    minutes = base / 60.0
    if increment:
        readable = "{:g} 分钟 + 每步 {:g} 秒".format(round(minutes, 1), increment)
    else:
        readable = "{:g} 分钟".format(round(minutes, 1))
    return TimeControl(
        base_seconds=int(base),
        increment_seconds=int(increment),
        estimated_seconds=int(estimated),
        speed=speed,
        speed_label_zh=label,
        readable_zh=readable,
    )
