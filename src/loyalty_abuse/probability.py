"""Abuse probability: score calibrator + published friction prior (noisy-OR)."""

from __future__ import annotations

from loyalty_abuse.schema import FrictionAction

# Defaults if calibration omits friction_p_floor — never invent certainty.
_DEFAULT_FRICTION_P_FLOOR = {
    "allow": 0.0,
    "throttle": 0.12,
    "soft_challenge": 0.32,
    "hard_challenge": 0.50,
    "block": 0.70,
}


def combine_score_and_friction_p(
    p_score: float,
    friction: FrictionAction | str,
    friction_p_floor: dict[str, float] | None = None,
) -> float:
    """Noisy-OR of score-calibrated p and friction-rung prior.

    Floors that raise friction without raising score must not leave p≈score-band
    (allow) while enforcement is hard_challenge. Priors are capped << 1 so
    score-14 + hard floor cannot claim p=1.0.
    """
    key = friction.value if isinstance(friction, FrictionAction) else str(friction)
    floors = friction_p_floor or _DEFAULT_FRICTION_P_FLOOR
    p_f = float(floors.get(key, 0.0))
    p_f = max(0.0, min(0.85, p_f))
    p_s = max(0.0, min(1.0, float(p_score)))
    return 1.0 - (1.0 - p_s) * (1.0 - p_f)
