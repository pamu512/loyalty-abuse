from __future__ import annotations

from loyalty_abuse.schema import FrictionAction

FRICTION_ORDER = [
    FrictionAction.allow,
    FrictionAction.throttle,
    FrictionAction.soft_challenge,
    FrictionAction.hard_challenge,
    FrictionAction.block,
]


def max_friction(a: FrictionAction, b: FrictionAction) -> FrictionAction:
    return a if FRICTION_ORDER.index(a) >= FRICTION_ORDER.index(b) else b


def apply_soft_floors(
    band: FrictionAction,
    *,
    snapshot: dict,
    confidences: dict[str, float],
    soft_floors: list[dict],
) -> tuple[FrictionAction, list[str]]:
    """Raise friction only; return (friction, reason codes fired)."""
    friction = band
    reasons: list[str] = []
    for floor in soft_floors:
        c = float(confidences.get(str(floor["typology"])) or 0.0)
        if c < float(floor["min_confidence"]):
            continue
        feature = floor.get("feature")
        min_feature = floor.get("min_feature")
        if feature is not None and min_feature is not None:
            if float(snapshot.get(feature) or 0) < float(min_feature):
                continue
        friction = max_friction(friction, FrictionAction(floor["min_friction"]))
        reasons.append(str(floor["reason"]))
    return friction, reasons
