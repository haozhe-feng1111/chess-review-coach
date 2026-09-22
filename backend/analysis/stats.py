"""Small, dependency-free statistics used by the player profile.

These exist so the app can say "35% (n=19, 95% 区间 24%–48%)" instead of a bare
percentage, and can refuse to call something a trend when the difference is inside the
noise. Everything here is deterministic and has no external dependencies — the numbers
must be reproducible and auditable, exactly like the chess facts.

No scipy, no pandas: the two functions below are all the statistics this MVP needs.
"""

import math
from typing import Optional, Tuple

#: 95% 置信区间的标准正态分位数。
Z_95 = 1.959963984540054


def wilson_interval(successes: int, total: int, z: float = Z_95) -> Tuple[float, float]:
    """Wilson score interval for a proportion — (low, high), both in [0, 1].

    Wilson rather than the textbook normal approximation because the interesting
    proportions here are often near 0 or 1 and the sample sizes are small, where the
    normal approximation produces intervals that run outside [0, 1] or collapse to a
    point. With ``total == 0`` the honest answer is "everything is possible" (0, 1).

    Reference: Wilson (1927); the same interval used by most A/B-test tooling.
    """
    if total <= 0:
        return 0.0, 1.0
    successes = max(0, min(successes, total))
    phat = successes / total
    denominator = 1 + z * z / total
    centre = phat + z * z / (2 * total)
    margin = z * math.sqrt(phat * (1 - phat) / total + z * z / (4 * total * total))
    low = (centre - margin) / denominator
    high = (centre + margin) / denominator
    # 4 位小数：这些值只用于展示和比较，四舍五入后输出稳定，
    # 不会出现 4.87e-17 这种"看着像 0 但不是 0"的浮点噪声。
    return round(max(0.0, low), 4), round(min(1.0, high), 4)


def two_proportion_z(
    successes_a: int, total_a: int, successes_b: int, total_b: int
) -> Optional[Tuple[float, float]]:
    """Two-sided z-test for ``p_a != p_b``; returns (z, p_value) or None if undefined.

    Used for "is this error type getting rarer?" — a claim the profile must not make
    unless the difference is bigger than sampling noise. Returns ``None`` when either
    side is empty or the pooled variance is zero (no information to test with).
    """
    if total_a <= 0 or total_b <= 0:
        return None
    successes_a = max(0, min(successes_a, total_a))
    successes_b = max(0, min(successes_b, total_b))
    p_a = successes_a / total_a
    p_b = successes_b / total_b
    pooled = (successes_a + successes_b) / (total_a + total_b)
    variance = pooled * (1 - pooled) * (1 / total_a + 1 / total_b)
    if variance <= 0:
        return None
    z = (p_a - p_b) / math.sqrt(variance)
    p_value = math.erfc(abs(z) / math.sqrt(2))
    return z, min(1.0, p_value)


def rate_per_100(successes: int, total: int) -> float:
    """A rate that stays readable when the denominator varies (games are not equal)."""
    if total <= 0:
        return 0.0
    return round(successes / total * 100.0, 2)
