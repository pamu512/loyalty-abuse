from __future__ import annotations

from typing import Any

from loyalty_abuse.calibration import load_calibration, sat_params
from loyalty_abuse.mathutil import sat
from loyalty_abuse.typologies._contrib import result


def score(snapshot: dict[str, Any]) -> TypologyResult:
    cal = load_calibration()
    a_r, b_r = sat_params("redeem_count_5m")
    a_s, b_s = sat_params("signup_count_5m")
    c_r = sat(float(snapshot.get("redeem_count_5m") or 0), a_r, b_r)
    c_s = sat(float(snapshot.get("signup_count_5m") or 0), a_s, b_s)
    c = max(c_r, c_s)
    young = float(cal.get("young_account_minutes") or 60)
    if float(snapshot.get("account_age_minutes") or 0) < young and c > 0:
        c = min(1.0, c * float(cal.get("young_bot_mult") or 1.15))
    reasons: list[str] = []
    if c_r > 0:
        reasons.append("bot.redeem_velocity")
    if c_s > 0:
        reasons.append("bot.signup_velocity")
    return result("bot_redeem", c, reasons)
