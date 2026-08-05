from loyalty_abuse.calibration import load_calibration
from loyalty_abuse.features import FeatureStore
from loyalty_abuse.schema import EventEnvelope, EventType


def _e(**kwargs):
    base = dict(
        event_id="e1",
        tenant_id="t1",
        ts="2026-08-04T12:00:00Z",
        type=EventType.signup,
        account_id="a1",
        session_id="s1",
        device_id="d1",
        ip="10.0.0.1",
        email="user@example.com",
        payload={},
    )
    base.update(kwargs)
    return EventEnvelope(**base)


def test_shared_device_linkage():
    store = FeatureStore()
    store.observe(_e(event_id="1", account_id="a1", device_id="devX", type=EventType.signup, ts="2026-08-04T12:00:00Z"))
    store.observe(_e(event_id="2", account_id="a2", device_id="devX", type=EventType.signup, ts="2026-08-04T12:01:00Z"))
    snap = store.snapshot(_e(event_id="3", account_id="a2", device_id="devX", type=EventType.redeem, ts="2026-08-04T12:02:00Z", payload={"offer_ids": []}))
    assert snap["accounts_on_device_24h"] >= 2


def test_ato_chain_flag():
    store = FeatureStore()
    store.observe(_e(event_id="1", type=EventType.signup, ts="2026-08-04T10:00:00Z", account_id="a1", device_id="old"))
    store.observe(
        _e(
            event_id="2",
            type=EventType.login,
            ts="2026-08-04T12:00:00Z",
            account_id="a1",
            device_id="new",
            payload={"success": True, "new_device": True, "geo": "XX"},
        )
    )
    store.observe(
        _e(
            event_id="3",
            type=EventType.profile_update,
            ts="2026-08-04T12:01:00Z",
            account_id="a1",
            device_id="new",
            payload={"fields_changed": ["email"]},
        )
    )
    snap = store.snapshot(
        _e(
            event_id="4",
            type=EventType.redeem,
            ts="2026-08-04T12:02:00Z",
            account_id="a1",
            device_id="new",
            payload={"reward_id": "r", "points": 50, "offer_ids": [], "channel": "app"},
        )
    )
    assert snap["ato_chain"] is True
    assert snap["force_hard_floor"] is True


def test_ato_chain_false_when_redeem_after_30m():
    store = FeatureStore()
    store.observe(_e(event_id="1", type=EventType.signup, ts="2026-08-04T10:00:00Z", account_id="a1", device_id="old"))
    store.observe(
        _e(
            event_id="2",
            type=EventType.login,
            ts="2026-08-04T12:00:00Z",
            account_id="a1",
            device_id="new",
            payload={"success": True, "new_device": True, "geo": "XX"},
        )
    )
    store.observe(
        _e(
            event_id="3",
            type=EventType.profile_update,
            ts="2026-08-04T12:01:00Z",
            account_id="a1",
            device_id="new",
            payload={"fields_changed": ["email"]},
        )
    )
    snap = store.snapshot(
        _e(
            event_id="4",
            type=EventType.redeem,
            ts="2026-08-04T12:31:00Z",
            account_id="a1",
            device_id="new",
            payload={"reward_id": "r", "points": 50, "offer_ids": [], "channel": "app"},
        )
    )
    assert snap["ato_chain"] is False
    assert snap["minutes_login_to_redeem"] is None


def test_ato_requires_new_device_not_bare_geo():
    store = FeatureStore()
    store.observe(_e(event_id="1", type=EventType.signup, ts="2026-08-04T10:00:00Z", account_id="a1", device_id="old"))
    store.observe(
        _e(
            event_id="2",
            type=EventType.login,
            ts="2026-08-04T12:00:00Z",
            account_id="a1",
            device_id="new",
            payload={"success": True, "geo": "XX"},
        )
    )
    store.observe(
        _e(
            event_id="3",
            type=EventType.profile_update,
            ts="2026-08-04T12:01:00Z",
            account_id="a1",
            device_id="new",
            payload={"fields_changed": ["email"]},
        )
    )
    snap = store.snapshot(
        _e(
            event_id="4",
            type=EventType.redeem,
            ts="2026-08-04T12:02:00Z",
            account_id="a1",
            device_id="new",
            payload={"reward_id": "r", "points": 50, "offer_ids": [], "channel": "app"},
        )
    )
    assert snap["ato_chain"] is False


def test_email_alias_burst_scoped_to_current_root():
    store = FeatureStore()
    store.observe(_e(event_id="1", account_id="a1", email="same+1@ex.com", ts="2026-08-04T12:00:00Z"))
    store.observe(_e(event_id="2", account_id="a2", email="same+2@ex.com", ts="2026-08-04T12:01:00Z"))
    store.observe(_e(event_id="3", account_id="a3", email="same+3@ex.com", ts="2026-08-04T12:02:00Z"))
    # unrelated burst on another root should not flag current account
    store.observe(_e(event_id="4", account_id="b1", email="other+1@ex.com", ts="2026-08-04T12:03:00Z"))
    store.observe(_e(event_id="5", account_id="b2", email="other+2@ex.com", ts="2026-08-04T12:04:00Z"))
    store.observe(_e(event_id="6", account_id="b3", email="other+3@ex.com", ts="2026-08-04T12:05:00Z"))
    snap_other = store.snapshot(
        _e(event_id="7", account_id="z1", email="lonely@ex.com", type=EventType.redeem, ts="2026-08-04T12:06:00Z", payload={})
    )
    assert snap_other["email_alias_burst"] is False
    snap_same = store.snapshot(
        _e(event_id="8", account_id="a1", email="same+9@ex.com", type=EventType.redeem, ts="2026-08-04T12:07:00Z", payload={})
    )
    assert snap_same["email_alias_burst"] is True


def test_velocity_counts_ignore_other_tenant():
    store = FeatureStore()
    store.observe(
        _e(
            event_id="1",
            tenant_id="t2",
            account_id="a9",
            device_id="devX",
            type=EventType.redeem,
            ts="2026-08-04T12:00:00Z",
        )
    )
    store.observe(
        _e(
            event_id="2",
            tenant_id="t2",
            account_id="a9",
            device_id="devX",
            type=EventType.signup,
            ts="2026-08-04T12:01:00Z",
        )
    )
    snap = store.snapshot(
        _e(
            event_id="3",
            tenant_id="t1",
            account_id="a1",
            device_id="devX",
            type=EventType.redeem,
            ts="2026-08-04T12:02:00Z",
            payload={"offer_ids": []},
        )
    )
    assert snap["redeem_count_5m"] == 0
    assert snap["signup_count_5m"] == 0


def test_force_hard_floor_uses_calibration_thresholds(monkeypatch):
    cal = load_calibration()
    monkeypatch.setattr(
        "loyalty_abuse.features.load_calibration",
        lambda: {**cal, "hard_floor": {"redeem_5m": 3, "signup_5m": 15}},
    )
    store = FeatureStore()
    for i in range(3):
        store.observe(
            _e(
                event_id=f"r{i}",
                type=EventType.redeem,
                ts=f"2026-08-04T12:0{i}:00Z",
                device_id="dev-bot",
                payload={"offer_ids": []},
            )
        )
    snap = store.snapshot(
        _e(
            event_id="r3",
            type=EventType.redeem,
            ts="2026-08-04T12:03:00Z",
            device_id="dev-bot",
            payload={"offer_ids": []},
        )
    )
    assert snap["redeem_count_5m"] == 3
    assert snap["force_hard_floor"] is True
