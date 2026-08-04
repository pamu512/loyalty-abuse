from __future__ import annotations

from typing import Any

from loyalty_abuse.schema import TypologyResult


def score(snapshot: dict[str, Any]) -> TypologyResult:
    points, reasons = 0, []
    if int(snapshot.get("accounts_on_device_24h") or 0) >= 3:
        points += 30
        reasons.append("multi_acct.shared_device_cluster")
    if snapshot.get("email_alias_burst"):
        points += 15
        reasons.append("multi_acct.email_alias_burst")
    return TypologyResult(id="multi_account", points=points, reasons=reasons)
