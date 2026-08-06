"""Friction-conditional p_abuse — auditor F1/F2."""

from loyalty_abuse.probability import combine_score_and_friction_p
from loyalty_abuse.schema import FrictionAction


def test_hard_floor_does_not_invent_certainty_at_low_score_p():
    p = combine_score_and_friction_p(0.05, FrictionAction.hard_challenge)
    assert 0.45 <= p <= 0.60
    assert p < 0.95


def test_allow_keeps_score_p():
    assert abs(combine_score_and_friction_p(0.2, FrictionAction.allow) - 0.2) < 1e-9


def test_block_raises_but_caps():
    p = combine_score_and_friction_p(0.1, FrictionAction.block)
    assert p >= 0.7
    assert p < 0.95
