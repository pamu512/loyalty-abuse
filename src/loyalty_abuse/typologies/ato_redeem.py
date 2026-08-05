from __future__ import annotations

from typing import Any

from loyalty_abuse.calibration import load_calibration
from loyalty_abuse.schema import TypologyResult
from loyalty_abuse.typologies._contrib import result


def score(snapshot: dict[str, Any]) -> TypologyResult:
    cal = load_calibration()
    if snapshot.get("ato_chain"):
        if snapshot.get("ato_known_device"):
            c = float(cal.get("ato_known_device_confidence") or 0.55)
            return result("ato_redeem", c, ["ato.login_profile_redeem_chain_known_device"])
        c = float(cal.get("ato_confidence") or 0.85)
        return result("ato_redeem", c, ["ato.login_profile_redeem_chain"])
    return result("ato_redeem", 0.0, [])
