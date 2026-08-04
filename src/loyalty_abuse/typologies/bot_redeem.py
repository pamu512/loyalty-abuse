from __future__ import annotations

from typing import Any

from loyalty_abuse.schema import TypologyResult


def score(snapshot: dict[str, Any]) -> TypologyResult:
    points, reasons = 0, []
    if int(snapshot.get("redeem_count_5m") or 0) >= 10:
        points += 30
        reasons.append("bot.redeem_velocity")
    if int(snapshot.get("signup_count_5m") or 0) >= 8:
        points += 20
        reasons.append("bot.signup_velocity")
    return TypologyResult(id="bot_redeem", points=points, reasons=reasons)
