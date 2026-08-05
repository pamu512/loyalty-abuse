import pytest

from loyalty_abuse.mathutil import sat


def test_sat_midpoint():
    assert sat(5, 0, 10) == 0.5


def test_sat_clamps():
    assert sat(-1, 0, 10) == 0.0
    assert sat(99, 0, 10) == 1.0


def test_sat_rejects_bad_range():
    with pytest.raises(ValueError):
        sat(1, 5, 5)
