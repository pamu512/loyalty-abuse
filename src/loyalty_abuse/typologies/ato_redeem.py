from __future__ import annotations

from typing import Any

from loyalty_abuse.schema import TypologyResult


def score(snapshot: dict[str, Any]) -> TypologyResult:
    points, reasons = 0, []
    if snapshot.get("ato_chain"):
        points += 40
        reasons.append("ato.login_profile_redeem_chain")
    return TypologyResult(id="ato_redeem", points=points, reasons=reasons)
