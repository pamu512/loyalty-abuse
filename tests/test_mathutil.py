import pytest

from loyalty_abuse.mathutil import sat, soft_or


def test_sat_midpoint():
    assert sat(5, 0, 10) == 0.5


def test_sat_clamps():
    assert sat(-1, 0, 10) == 0.0
    assert sat(99, 0, 10) == 1.0


def test_sat_rejects_bad_range():
    with pytest.raises(ValueError):
        sat(1, 5, 5)


def test_soft_or_empty():
    assert soft_or([]) == 0.0


def test_soft_or_single():
    assert soft_or([0.5]) == 0.5


def test_soft_or_independent():
    # 1 - (1-0.5)*(1-0.5) = 0.75
    assert abs(soft_or([0.5, 0.5]) - 0.75) < 1e-9


def test_soft_or_clips():
    assert soft_or([-1.0, 2.0]) == 1.0
