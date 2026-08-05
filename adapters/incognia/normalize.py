"""Map raw Incognia assessment JSON → IncogniaSignals."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class IncogniaSignals:
    risk_assessment: str  # low_risk | high_risk | unknown_risk
    tamper_suspected: bool
    emulator: bool
    gps_spoofing: bool
    location_permission_enabled: bool | None
    device_fraud_reputation: str | None
    known_account: bool | None
    raw_id: str | None
    source: str  # fixture | live | unavailable


_ALLOWED_RISK = frozenset({"low_risk", "high_risk", "unknown_risk"})


def normalize_assessment(raw: dict[str, Any], *, source: str) -> IncogniaSignals:
    """Normalize a snake_case Incognia assessment dict into IncogniaSignals."""
    if not isinstance(raw, dict):
        raise TypeError("raw assessment must be a dict")

    evidence = raw.get("evidence")
    if not isinstance(evidence, dict):
        evidence = {}

    integrity = evidence.get("device_integrity")
    if not isinstance(integrity, dict):
        integrity = {}

    location = evidence.get("location_services")
    if not isinstance(location, dict):
        location = {}

    risk = raw.get("risk_assessment")
    if risk not in _ALLOWED_RISK:
        risk = "unknown_risk"

    raw_id = raw.get("id")
    if raw_id is not None:
        raw_id = str(raw_id)

    loc_perm = location.get("location_permission_enabled")
    if loc_perm is not None:
        loc_perm = bool(loc_perm)

    reputation = evidence.get("device_fraud_reputation")
    if reputation is not None:
        reputation = str(reputation)

    known = evidence.get("known_account")
    if known is not None:
        known = bool(known)

    # ponytail: tamper_suspected ≡ probable_root; widen if live sandbox adds app_cloner etc.
    return IncogniaSignals(
        risk_assessment=risk,
        tamper_suspected=bool(integrity.get("probable_root", False)),
        emulator=bool(integrity.get("emulator", False)),
        gps_spoofing=bool(integrity.get("gps_spoofing", False)),
        location_permission_enabled=loc_perm,
        device_fraud_reputation=reputation,
        known_account=known,
        raw_id=raw_id,
        source=source,
    )
