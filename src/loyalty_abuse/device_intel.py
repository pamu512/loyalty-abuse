"""Normalized device-intel payload helpers. Core never imports adapters/incognia."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

INTEL_HIGH_RISK_REASON = "intel.incognia_high_risk"
INTEL_UNAVAILABLE_REASON = "intel.incognia_unavailable"

_SIGNAL_KEYS = (
    "risk_assessment",
    "tamper_suspected",
    "emulator",
    "gps_spoofing",
    "location_permission_enabled",
    "device_fraud_reputation",
    "known_account",
    "raw_id",
    "source",
)


def _sig_get(signals: Any, key: str, default: Any = None) -> Any:
    if isinstance(signals, Mapping):
        return signals.get(key, default)
    return getattr(signals, key, default)


def apply_to_payload(payload: dict, signals: Any) -> dict:
    """Merge normalized intel onto payload under nested ``device_intel`` (plain dicts)."""
    out = dict(payload)
    di = dict(out["device_intel"]) if isinstance(out.get("device_intel"), dict) else {}
    for key in _SIGNAL_KEYS:
        di[key] = _sig_get(signals, key)
    # bools: coerce when present-ish; leave None for optional fields as-is from signals
    for bool_key in ("tamper_suspected", "emulator", "gps_spoofing"):
        di[bool_key] = bool(di.get(bool_key))
    if di.get("risk_assessment") not in {"low_risk", "high_risk", "unknown_risk"}:
        di["risk_assessment"] = "unknown_risk"
    out["device_intel"] = di
    return out


def _device_intel(snapshot_or_payload: dict) -> dict:
    di = snapshot_or_payload.get("device_intel")
    return di if isinstance(di, dict) else {}


def intel_signals_hard_floor(snapshot_or_payload: dict) -> bool:
    """True when present signals warrant ≥ hard_challenge (not fail-closed flag)."""
    di = _device_intel(snapshot_or_payload)
    if di.get("risk_assessment") == "high_risk":
        return True
    if di.get("tamper_suspected") is True:
        return True
    if di.get("emulator") is True:
        return True
    return False


def intel_force_hard_floor(snapshot_or_payload: dict) -> bool:
    """True if high_risk / tamper / emulator, or Task-4 fail-closed force-block flag."""
    if snapshot_or_payload.get("device_intel_force_block") is True:
        return True
    return intel_signals_hard_floor(snapshot_or_payload)


def intel_unavailable(snapshot_or_payload: dict) -> bool:
    return _device_intel(snapshot_or_payload).get("source") == "unavailable"
