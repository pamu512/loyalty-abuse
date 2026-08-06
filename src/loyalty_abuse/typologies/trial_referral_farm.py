from __future__ import annotations

from typing import Any

from loyalty_abuse.calibration import sat_params
from loyalty_abuse.mathutil import sat, soft_or
from loyalty_abuse.schema import TypologyResult
from loyalty_abuse.typologies._contrib import result


def score(snapshot: dict[str, Any]) -> TypologyResult:
    """Signup perk / referral farming cycles (multi-account trial abuse)."""
    cycles = sat(
        float(snapshot.get("trial_referral_cycles_7d") or 0),
        *sat_params("trial_referral_cycles_7d"),
    )
    welcome = 1.0 if snapshot.get("welcome_offer_claimed") else 0.0
    referral_burst = sat(
        float(snapshot.get("accounts_on_device_24h") or 0),
        *sat_params("accounts_on_device_24h"),
    )
    c = soft_or([cycles, cycles * welcome, welcome * referral_burst * 0.7])
    reasons: list[str] = []
    if cycles > 0:
        reasons.append("trial_referral.cycle_velocity")
    if welcome and referral_burst > 0:
        reasons.append("trial_referral.welcome_multi_acct")
    return result("trial_referral_farm", c, reasons)
