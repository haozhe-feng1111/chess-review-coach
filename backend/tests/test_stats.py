"""档案里用到的统计：置信区间与两比例检验。

这些数字会被写在界面上（"35%（n=19，95% 区间 24%–48%）"），所以必须可核实：
测试里用的是教科书/在线计算器都能查到的已知值，而不是"跑一遍看输出"。
"""

import pytest

from analysis.stats import rate_per_100, two_proportion_z, wilson_interval


def test_wilson_interval_matches_known_values():
    # 19/43 ≈ 0.442，95% Wilson 区间约为 (0.303, 0.589)
    low, high = wilson_interval(19, 43)
    assert low == pytest.approx(0.303, abs=0.002)
    assert high == pytest.approx(0.589, abs=0.002)

    # 3/10 = 0.3 → (0.108, 0.603)
    low, high = wilson_interval(3, 10)
    assert low == pytest.approx(0.108, abs=0.002)
    assert high == pytest.approx(0.603, abs=0.002)


def test_wilson_interval_stays_inside_zero_and_one():
    """小样本、极端比例是常态（"3 局里 0 次"），区间不能跑出 [0,1]。"""
    low, high = wilson_interval(0, 3)
    assert low == 0.0
    assert 0.5 < high < 0.75  # 0/3 的区间上界约 0.69

    low, high = wilson_interval(3, 3)
    assert 0.25 < low < 0.5  # 3/3 的区间下界约 0.31
    assert high == 1.0


def test_wilson_interval_without_samples_says_everything_is_possible():
    assert wilson_interval(0, 0) == (0.0, 1.0)


def test_two_proportion_z_detects_a_real_difference():
    # 43 手里 19 次 vs 45 手里 4 次：差得很明显
    result = two_proportion_z(19, 43, 4, 45)
    assert result is not None
    z, p_value = result
    assert z > 3
    assert p_value < 0.01


def test_two_proportion_z_refuses_to_call_noise_a_trend():
    """3/10 vs 4/11 这种差别在噪声范围内，p 值必须大到不能下结论。"""
    result = two_proportion_z(3, 10, 4, 11)
    assert result is not None
    _z, p_value = result
    assert p_value > 0.5


def test_two_proportion_z_without_data_returns_nothing():
    assert two_proportion_z(0, 0, 1, 10) is None
    assert two_proportion_z(0, 10, 0, 0) is None
    # 两边都是 0 次：没有信息可检验
    assert two_proportion_z(0, 10, 0, 10) is None


def test_rate_per_100_handles_empty_denominator():
    assert rate_per_100(5, 50) == 10.0
    assert rate_per_100(0, 0) == 0.0
