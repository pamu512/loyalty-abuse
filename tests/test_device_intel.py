"""Core device_intel friction floor — no adapter imports."""

from types import SimpleNamespace

from loyalty_abuse import evaluate
from loyalty_abuse.device_intel import apply_to_payload, intel_force_hard_floor
from loyalty_abuse.features import FeatureStore
from loyalty_abuse.schema import EventEnvelope, EventType, FrictionAction


def _clean_redeem(*, payload: dict) -> EventEnvelope:
    return EventEnvelope(
        event_id="r1",
        tenant_id="t",
        ts="2026-08-04T12:00:00Z",
        type=EventType.redeem,
        account_id="a",
        session_id="s",
        device_id="d",
        ip="1.1.1.1",
        payload=payload,
    )


def test_apply_to_payload_sets_nested_device_intel_from_plain_mapping():
    out = apply_to_payload(
        {"reward_id": "r"},
        {
            "risk_assessment": "high_risk",
            "tamper_suspected": True,
            "emulator": False,
            "gps_spoofing": True,
            "location_permission_enabled": True,
            "device_fraud_reputation": "high_risk",
            "known_account": False,
            "raw_id": "abc",
            "source": "fixture",
        },
    )
    assert out["reward_id"] == "r"
    assert out["device_intel"]["risk_assessment"] == "high_risk"
    assert out["device_intel"]["tamper_suspected"] is True
    assert out["device_intel"]["emulator"] is False
    assert out["device_intel"]["source"] == "fixture"


def test_apply_to_payload_accepts_attribute_object():
    signals = SimpleNamespace(
        risk_assessment="low_risk",
        tamper_suspected=False,
        emulator=True,
        gps_spoofing=False,
        location_permission_enabled=None,
        device_fraud_reputation=None,
        known_account=None,
        raw_id=None,
        source="live",
    )
    out = apply_to_payload({}, signals)
    assert out["device_intel"]["emulator"] is True
    assert out["device_intel"]["risk_assessment"] == "low_risk"


def test_intel_force_hard_floor_high_risk_tamper_emulator():
    assert intel_force_hard_floor({"device_intel": {"risk_assessment": "high_risk"}}) is True
    assert intel_force_hard_floor({"device_intel": {"tamper_suspected": True}}) is True
    assert intel_force_hard_floor({"device_intel": {"emulator": True}}) is True
    assert intel_force_hard_floor({"device_intel": {"risk_assessment": "low_risk"}}) is False
    assert intel_force_hard_floor({}) is False


def test_intel_force_hard_floor_honors_force_block_flag():
    assert intel_force_hard_floor({"device_intel_force_block": True}) is True
    assert intel_force_hard_floor({"device_intel_force_block": False}) is False


def test_high_risk_payload_forces_hard_challenge_on_clean_redeem():
    store = FeatureStore()
    store.observe(
        EventEnvelope(
            event_id="s1",
            tenant_id="t",
            ts="2026-08-01T00:00:00Z",
            type=EventType.signup,
            account_id="a",
            session_id="s",
            device_id="d",
            ip="1.1.1.1",
            payload={},
        )
    )
    payload = apply_to_payload(
        {"reward_id": "r", "points": 10, "offer_ids": ["one"], "channel": "app"},
        {
            "risk_assessment": "high_risk",
            "tamper_suspected": False,
            "emulator": False,
            "gps_spoofing": False,
            "location_permission_enabled": None,
            "device_fraud_reputation": None,
            "known_account": None,
            "raw_id": None,
            "source": "fixture",
        },
    )
    d = evaluate(_clean_redeem(payload=payload), store)
    assert d.friction in {FrictionAction.hard_challenge, FrictionAction.block}
    assert d.score < 25
    assert "intel.incognia_high_risk" in d.reasons
    assert d.features_snapshot.get("force_hard_floor") is True


def test_low_risk_payload_no_intel_floor():
    store = FeatureStore()
    store.observe(
        EventEnvelope(
            event_id="s1",
            tenant_id="t",
            ts="2026-08-01T00:00:00Z",
            type=EventType.signup,
            account_id="a",
            session_id="s",
            device_id="d",
            ip="1.1.1.1",
            payload={},
        )
    )
    payload = apply_to_payload(
        {"reward_id": "r", "points": 10, "offer_ids": ["one"], "channel": "app"},
        {
            "risk_assessment": "low_risk",
            "tamper_suspected": False,
            "emulator": False,
            "gps_spoofing": False,
            "location_permission_enabled": None,
            "device_fraud_reputation": None,
            "known_account": None,
            "raw_id": None,
            "source": "fixture",
        },
    )
    d = evaluate(_clean_redeem(payload=payload), store)
    assert d.friction == FrictionAction.allow
    assert "intel.incognia_high_risk" not in d.reasons


def test_device_intel_force_block_forces_hard_floor_without_high_risk_reason():
    store = FeatureStore()
    store.observe(
        EventEnvelope(
            event_id="s1",
            tenant_id="t",
            ts="2026-08-01T00:00:00Z",
            type=EventType.signup,
            account_id="a",
            session_id="s",
            device_id="d",
            ip="1.1.1.1",
            payload={},
        )
    )
    d = evaluate(
        _clean_redeem(
            payload={
                "reward_id": "r",
                "points": 10,
                "offer_ids": ["one"],
                "channel": "app",
                "device_intel_force_block": True,
            }
        ),
        store,
    )
    assert d.friction in {FrictionAction.hard_challenge, FrictionAction.block}
    assert "intel.incognia_high_risk" not in d.reasons
