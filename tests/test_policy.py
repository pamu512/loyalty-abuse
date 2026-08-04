from loyalty_abuse.policy import FrictionPolicy
from loyalty_abuse.schema import FrictionAction


def test_default_bands():
    p = FrictionPolicy()
    assert p.action_for(0) == FrictionAction.allow
    assert p.action_for(24) == FrictionAction.allow
    assert p.action_for(25) == FrictionAction.throttle
    assert p.action_for(44) == FrictionAction.throttle
    assert p.action_for(45) == FrictionAction.soft_challenge
    assert p.action_for(64) == FrictionAction.soft_challenge
    assert p.action_for(65) == FrictionAction.hard_challenge
    assert p.action_for(84) == FrictionAction.hard_challenge
    assert p.action_for(85) == FrictionAction.block
    assert p.action_for(100) == FrictionAction.block


def test_hard_override_floor():
    p = FrictionPolicy()
    assert p.action_for(10, force_hard_floor=True) == FrictionAction.hard_challenge
    assert p.action_for(90, force_hard_floor=True) == FrictionAction.block
