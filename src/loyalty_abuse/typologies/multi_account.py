from __future__ import annotations

from typing import Any

from loyalty_abuse.calibration import load_calibration, sat_params
from loyalty_abuse.mathutil import sat, soft_or
from loyalty_abuse.schema import TypologyResult
from loyalty_abuse.typologies._contrib import result


def score(snapshot: dict[str, Any]) -> TypologyResult:
    cal = load_calibration()
    c_dev = soft_or(
        [
            sat(float(snapshot.get("accounts_on_device_1h") or 0), *sat_params("accounts_on_device_1h")),
            sat(float(snapshot.get("accounts_on_device_24h") or 0), *sat_params("accounts_on_device_24h")),
            sat(float(snapshot.get("accounts_on_device_7d") or 0), *sat_params("accounts_on_device_7d")),
        ]
    )
    c_ip = soft_or(
        [
            sat(float(snapshot.get("accounts_on_ip_1h") or 0), *sat_params("accounts_on_ip_1h")),
            sat(float(snapshot.get("accounts_on_ip_24h") or 0), *sat_params("accounts_on_ip_24h")),
            sat(float(snapshot.get("accounts_on_ip_7d") or 0), *sat_params("accounts_on_ip_7d")),
        ]
    )
    c_email = (
        float(cal.get("email_burst_confidence") or 0.75) if snapshot.get("email_alias_burst") else 0.0
    )
    c = soft_or([c_dev, c_ip, c_email])
    young = float(cal.get("young_account_minutes") or 60)
    if float(snapshot.get("account_age_minutes") or 0) < young and int(
        snapshot.get("accounts_on_device_24h") or 0
    ) >= 2:
        c = min(1.0, c * float(cal.get("young_multi_mult") or 1.1))
    reasons: list[str] = []
    if c_dev > 0:
        reasons.append("multi_acct.shared_device_cluster")
    if c_ip > 0 and c_ip >= c_dev:
        reasons.append("multi_acct.shared_ip_cluster")
    if c_email > 0:
        reasons.append("multi_acct.email_alias_burst")
    return result("multi_account", c, reasons)
