from __future__ import annotations

from typing import Any

from loyalty_abuse.calibration import sat_params
from loyalty_abuse.mathutil import sat, soft_or
from loyalty_abuse.schema import TypologyResult
from loyalty_abuse.typologies._contrib import result


def score(snapshot: dict[str, Any]) -> TypologyResult:
    """Partner / cross-merchant promo code farming across accounts."""
    partner = 1.0 if snapshot.get("partner_promo_code") else 0.0
    accts = sat(
        float(snapshot.get("partner_code_accounts_24h") or 0),
        *sat_params("partner_code_accounts_24h"),
    )
    multi = sat(
        float(snapshot.get("accounts_on_device_24h") or 0),
        *sat_params("accounts_on_device_24h"),
    )
    c = soft_or([accts * partner, accts * multi * partner])
    reasons: list[str] = []
    if accts > 0 and partner:
        reasons.append("partner_promo.code_concentration")
    if multi > 0 and partner and accts > 0:
        reasons.append("partner_promo.multi_acct_farm")
    return result("partner_promo_farm", c, reasons)
