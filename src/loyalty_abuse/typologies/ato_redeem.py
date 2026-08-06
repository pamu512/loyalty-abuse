from __future__ import annotations

from typing import Any

from loyalty_abuse.calibration import load_calibration
from loyalty_abuse.schema import TypologyResult
from loyalty_abuse.typologies._contrib import result


def score(snapshot: dict[str, Any]) -> TypologyResult:
    cal = load_calibration()
    from loyalty_abuse.mathutil import soft_or

    channels: list[float] = []
    reasons: list[str] = []
    if snapshot.get("ato_chain"):
        known = bool(snapshot.get("ato_known_device"))
        base = float(
            cal.get("ato_known_device_confidence")
            if known
            else cal.get("ato_confidence")
            or 0.85
        )
        if known and base == 0.0:
            base = 0.55
        mins = snapshot.get("minutes_login_to_redeem")
        if mins is not None:
            urgency = max(0.0, min(1.0, 1.0 - float(mins) / 30.0))
            boost = float(cal.get("ato_urgency_boost") or 0.22)
            base = min(1.0, base + boost * urgency)
        channels.append(base)
        reasons.append(
            "ato.login_profile_redeem_chain_known_device"
            if known
            else "ato.login_profile_redeem_chain"
        )
    intel = snapshot.get("device_intel") if isinstance(snapshot.get("device_intel"), dict) else {}
    risk = str(intel.get("risk_assessment") or intel.get("device_risk") or "").lower()
    if risk in {"high_risk", "high", "account_takeover"}:
        channels.append(0.75)
        reasons.append("ato.device_intel_high_risk")
    elif snapshot.get("device_intel_force_block"):
        channels.append(0.9)
        reasons.append("ato.device_intel_force_block")
    if not channels:
        return result("ato_redeem", 0.0, [])
    return result("ato_redeem", soft_or(channels), reasons)
