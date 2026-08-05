"""Decision economics: liability and expected loss / insult (USD per decision)."""

from __future__ import annotations

from typing import Any

from loyalty_abuse.calibration import load_calibration
from loyalty_abuse.schema import EventEnvelope, FrictionAction

_MONEY_KEYS = ("points_liability_usd", "discount_usd", "referral_bonus_usd")


def liability_usd(event: EventEnvelope) -> float:
    payload = event.payload or {}
    total = 0.0
    for key in _MONEY_KEYS:
        raw = payload.get(key)
        if raw is None:
            continue
        total += float(raw)
    return total


def _cost_block(cost: dict[str, Any] | None = None) -> dict[str, Any]:
    if cost is not None:
        return cost
    cal = load_calibration()
    block = cal.get("cost")
    if not isinstance(block, dict):
        raise ValueError("calibration missing cost block")
    return block


def _friction_key(friction: FrictionAction | str) -> str:
    return friction.value if isinstance(friction, FrictionAction) else str(friction)


def expected_loss_usd(
    liability: float,
    p_abuse: float,
    friction: FrictionAction | str,
    cost: dict[str, Any] | None = None,
) -> float:
    """USD expected loss ≈ C_fn_per_usd * liability * p_abuse * miss_fraction[friction]."""
    block = _cost_block(cost)
    c_fn = float(block["C_fn_per_usd"])
    miss = block.get("miss_fraction") or {}
    key = _friction_key(friction)
    if key not in miss:
        raise KeyError(f"miss_fraction missing friction {key!r}")
    return c_fn * float(liability) * float(p_abuse) * float(miss[key])


def expected_insult_usd(
    friction: FrictionAction | str,
    cost: dict[str, Any] | None = None,
) -> float:
    """USD expected insult ≈ C_fp[friction]."""
    block = _cost_block(cost)
    c_fp = block.get("C_fp") or {}
    key = _friction_key(friction)
    if key not in c_fp:
        raise KeyError(f"C_fp missing friction {key!r}")
    return float(c_fp[key])


def expected_costs(
    liability: float,
    p_abuse: float,
    friction: FrictionAction | str,
    cost: dict[str, Any] | None = None,
) -> tuple[float, float]:
    """Return (expected_loss_usd, expected_insult_usd) in USD per decision."""
    block = _cost_block(cost)
    return (
        expected_loss_usd(liability, p_abuse, friction, cost=block),
        expected_insult_usd(friction, cost=block),
    )
