from __future__ import annotations

from typing import Any

from loyalty_abuse.schema import TypologyResult


def score(snapshot: dict[str, Any]) -> TypologyResult:
    points, reasons = 0, []
    if snapshot.get("referral_shared_device"):
        points += 30
        reasons.append("referral.shared_device")
    if snapshot.get("referral_shared_payment"):
        points += 20
        reasons.append("referral.shared_payment")
    return TypologyResult(id="referral_self_deal", points=points, reasons=reasons)
