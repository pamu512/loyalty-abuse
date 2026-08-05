from __future__ import annotations

from typing import Any

from loyalty_abuse.calibration import sat_params
from loyalty_abuse.mathutil import sat
from loyalty_abuse.typologies._contrib import result


def score(snapshot: dict[str, Any]) -> TypologyResult:
    a, b = sat_params("code_unique_users_24h")
    c = sat(float(snapshot.get("code_unique_users_24h") or 0), a, b)
    reasons = ["code.unique_user_spike"] if c > 0 else []
    return result("code_leak", c, reasons)
