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
