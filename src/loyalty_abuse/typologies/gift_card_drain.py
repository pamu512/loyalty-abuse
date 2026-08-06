from __future__ import annotations

from typing import Any

from loyalty_abuse.calibration import sat_params
from loyalty_abuse.mathutil import sat, soft_or
from loyalty_abuse.schema import TypologyResult
from loyalty_abuse.typologies._contrib import result


def score(snapshot: dict[str, Any]) -> TypologyResult:
    """Fast gift-card / stored-value load→burn with payment instrument churn."""
    minutes = float(snapshot.get("gift_card_load_burn_minutes") or 1e9)
    # Invert: faster load→burn → higher confidence.
    speed = 0.0
    if minutes < 1e8:
        # sat on inverse-ish: treat (120 - minutes) clipped
        speed = sat(max(0.0, 120.0 - minutes), *sat_params("gift_card_load_burn_minutes"))
    churn = sat(
        float(snapshot.get("gift_card_instrument_churn") or 0),
        *sat_params("gift_card_instrument_churn"),
    )
    load_flag = 1.0 if snapshot.get("gift_card_load_event") else 0.0
    c = soft_or([speed * load_flag, churn, speed * churn])
    reasons: list[str] = []
    if speed > 0 and load_flag:
        reasons.append("gift_card.fast_load_burn")
    if churn > 0:
        reasons.append("gift_card.instrument_churn")
    return result("gift_card_drain", c, reasons)
