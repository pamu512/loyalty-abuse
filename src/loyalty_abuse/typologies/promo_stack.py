from __future__ import annotations

from typing import Any

from loyalty_abuse.schema import TypologyResult


def score(snapshot: dict[str, Any]) -> TypologyResult:
    points, reasons = 0, []
    if int(snapshot.get("stack_depth") or 0) >= 3:
        points += 20
        reasons.append("promo.stack_depth")
    if float(snapshot.get("discount_depth") or 0) >= 50:
        points += 15
        reasons.append("promo.discount_depth")
    return TypologyResult(id="promo_stack", points=points, reasons=reasons)
