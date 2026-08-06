from __future__ import annotations

from typing import Any

from loyalty_abuse.calibration import load_calibration
from loyalty_abuse.schema import TypologyResult
from loyalty_abuse.typologies._contrib import result


def score(snapshot: dict[str, Any]) -> TypologyResult:
    cal = load_calibration()
    if not snapshot.get("ato_chain"):
        return result("ato_redeem", 0.0, [])
    known = bool(snapshot.get("ato_known_device"))
    base = float(
        cal.get("ato_known_device_confidence")
        if known
        else cal.get("ato_confidence")
        or 0.85
    )
    if known and base == 0.0:
        base = 0.55
    # Urgency: faster login→redeem raises confidence (score variance on ATO slice).
    mins = snapshot.get("minutes_login_to_redeem")
    if mins is not None:
        urgency = max(0.0, min(1.0, 1.0 - float(mins) / 30.0))
        boost = float(cal.get("ato_urgency_boost") or 0.22)
        base = min(1.0, base + boost * urgency)
    reason = (
        "ato.login_profile_redeem_chain_known_device"
        if known
        else "ato.login_profile_redeem_chain"
    )
    return result("ato_redeem", base, [reason])
