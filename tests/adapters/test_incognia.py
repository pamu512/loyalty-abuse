"""Incognia adapter: normalize_assessment + pinned fixtures."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).resolve().parents[2] / "adapters" / "incognia" / "fixtures"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_normalize_login_low_risk_fixture():
    from adapters.incognia import normalize_assessment

    raw = _load("login_low_risk.json")
    signals = normalize_assessment(raw, source="fixture")

    assert signals.risk_assessment == "low_risk"
    assert signals.tamper_suspected is False
    assert signals.emulator is False
    assert signals.gps_spoofing is False
    assert signals.location_permission_enabled is True
    assert signals.device_fraud_reputation == "allowed"
    assert signals.known_account is True
    assert signals.raw_id == "fix-login-low"
    assert signals.source == "fixture"


def test_normalize_login_high_risk_fixture():
    from adapters.incognia import normalize_assessment

    raw = _load("login_high_risk.json")
    signals = normalize_assessment(raw, source="fixture")

    assert signals.risk_assessment == "high_risk"
    assert signals.tamper_suspected is True
    assert signals.emulator is True
    assert signals.gps_spoofing is False
    assert signals.location_permission_enabled is False
    assert signals.device_fraud_reputation == "unknown"
    assert signals.known_account is False
    assert signals.raw_id == "fix-login-high"
    assert signals.source == "fixture"


def test_normalize_missing_evidence_defaults():
    from adapters.incognia import normalize_assessment

    signals = normalize_assessment(
        {"id": "bare", "risk_assessment": "unknown_risk"},
        source="unavailable",
    )
    assert signals.risk_assessment == "unknown_risk"
    assert signals.tamper_suspected is False
    assert signals.emulator is False
    assert signals.gps_spoofing is False
    assert signals.location_permission_enabled is None
    assert signals.device_fraud_reputation is None
    assert signals.known_account is None
    assert signals.raw_id == "bare"
    assert signals.source == "unavailable"


def test_incognia_signals_is_frozen():
    from adapters.incognia import IncogniaSignals

    s = IncogniaSignals(
        risk_assessment="low_risk",
        tamper_suspected=False,
        emulator=False,
        gps_spoofing=False,
        location_permission_enabled=True,
        device_fraud_reputation="allowed",
        known_account=True,
        raw_id="x",
        source="fixture",
    )
    with pytest.raises(Exception):
        s.risk_assessment = "high_risk"  # type: ignore[misc]
