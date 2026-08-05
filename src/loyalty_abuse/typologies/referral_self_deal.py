from __future__ import annotations

from typing import Any

from loyalty_abuse.calibration import load_calibration
from loyalty_abuse.mathutil import soft_or
from loyalty_abuse.schema import TypologyResult
from loyalty_abuse.typologies._contrib import result


def score(snapshot: dict[str, Any]) -> TypologyResult:
    cal = load_calibration()
    shared_d = bool(snapshot.get("referral_shared_device"))
    shared_p = bool(snapshot.get("referral_shared_payment"))
    if shared_d and shared_p:
        # both channels: keep calibrated both-c override (not soft_or of the two)
        c = float(cal.get("referral_both_c") or 1.0)
    else:
        channels: list[float] = []
        if shared_d:
            channels.append(float(cal.get("referral_shared_device_c") or 0.9))
        if shared_p:
            channels.append(float(cal.get("referral_shared_payment_c") or 0.85))
        c = soft_or(channels)
    reasons: list[str] = []
    if shared_d:
        reasons.append("referral.shared_device")
    if shared_p:
        reasons.append("referral.shared_payment")
    return result("referral_self_deal", c, reasons)
