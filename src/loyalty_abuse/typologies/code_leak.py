from __future__ import annotations

from typing import Any

from loyalty_abuse.schema import TypologyResult


def score(snapshot: dict[str, Any]) -> TypologyResult:
    points, reasons = 0, []
    if int(snapshot.get("code_unique_users_24h") or 0) >= 25:
        points += 25
        reasons.append("code.unique_user_spike")
    return TypologyResult(id="code_leak", points=points, reasons=reasons)
