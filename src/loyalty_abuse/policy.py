from __future__ import annotations

from dataclasses import dataclass

from loyalty_abuse.schema import FrictionAction, POLICY_VERSION


@dataclass(frozen=True)
class FrictionPolicy:
    allow_max: int = 24
    throttle_max: int = 44
    soft_max: int = 64
    hard_max: int = 84
    version: str = POLICY_VERSION

    def action_for(self, score: int, *, force_hard_floor: bool = False) -> FrictionAction:
        s = max(0, min(100, int(score)))
        if s <= self.allow_max:
            action = FrictionAction.allow
        elif s <= self.throttle_max:
            action = FrictionAction.throttle
        elif s <= self.soft_max:
            action = FrictionAction.soft_challenge
        elif s <= self.hard_max:
            action = FrictionAction.hard_challenge
        else:
            action = FrictionAction.block
        if force_hard_floor:
            order = [
                FrictionAction.allow,
                FrictionAction.throttle,
                FrictionAction.soft_challenge,
                FrictionAction.hard_challenge,
                FrictionAction.block,
            ]
            if order.index(action) < order.index(FrictionAction.hard_challenge):
                return FrictionAction.hard_challenge
        return action
