from __future__ import annotations

from typing import Any

from loyalty_abuse.calibration import sat_params
from loyalty_abuse.mathutil import sat, soft_or
from loyalty_abuse.schema import TypologyResult
from loyalty_abuse.typologies._contrib import result


def score(snapshot: dict[str, Any]) -> TypologyResult:
    a_s, b_s = sat_params("stack_depth")
    a_d, b_d = sat_params("discount_depth")
    c_stack = sat(float(snapshot.get("stack_depth") or 0), a_s, b_s)
    c_disc = sat(float(snapshot.get("discount_depth") or 0), a_d, b_d)
    c = soft_or([c_stack, c_disc])
    reasons: list[str] = []
    if c_stack > 0:
        reasons.append("promo.stack_depth")
    if c_disc > 0:
        reasons.append("promo.discount_depth")
    return result("promo_stack", c, reasons)
