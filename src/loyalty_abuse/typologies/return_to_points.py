from __future__ import annotations

from typing import Any

from loyalty_abuse.calibration import sat_params
from loyalty_abuse.mathutil import sat, soft_or
from loyalty_abuse.schema import TypologyResult
from loyalty_abuse.typologies._contrib import result


def score(snapshot: dict[str, Any]) -> TypologyResult:
    """Refund/cancel → points restore → re-burn cycles."""
    cycles = sat(
        float(snapshot.get("return_points_cycles_7d") or 0),
        *sat_params("return_points_cycles_7d"),
    )
    restore = 1.0 if snapshot.get("points_restored_after_refund") else 0.0
    reburn = 1.0 if snapshot.get("reburn_after_restore") else 0.0
    c = soft_or([cycles, cycles * restore * reburn, restore * reburn * 0.8])
    reasons: list[str] = []
    if cycles > 0:
        reasons.append("return_points.cycle_velocity")
    if restore and reburn:
        reasons.append("return_points.restore_reburn")
    return result("return_to_points", c, reasons)
