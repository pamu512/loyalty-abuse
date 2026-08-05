from __future__ import annotations

from typing import Any

from loyalty_abuse.calibration import sat_params
from loyalty_abuse.mathutil import sat, soft_or
from loyalty_abuse.schema import TypologyResult
from loyalty_abuse.typologies._contrib import result


def score(snapshot: dict[str, Any]) -> TypologyResult:
    c = soft_or(
        [
            sat(float(snapshot.get("code_unique_users_1h") or 0), *sat_params("code_unique_users_1h")),
            sat(float(snapshot.get("code_unique_users_24h") or 0), *sat_params("code_unique_users_24h")),
            sat(float(snapshot.get("code_unique_users_7d") or 0), *sat_params("code_unique_users_7d")),
        ]
    )
    reasons = ["code.unique_user_spike"] if c > 0 else []
    return result("code_leak", c, reasons)
