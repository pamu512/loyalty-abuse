from __future__ import annotations

from datetime import datetime, timezone

from loyalty_abuse.features import FeatureStore
from loyalty_abuse.graph import cluster_features
from loyalty_abuse.schema import EventEnvelope, EventType


def _e(
    eid: str,
    acct: str,
    *,
    device: str = "dX",
    phone: str | None = None,
    email: str | None = None,
    pay: str | None = None,
    ts: str = "2026-08-05T12:00:00Z",
    etype: EventType = EventType.signup,
    payload: dict | None = None,
) -> EventEnvelope:
    return EventEnvelope(
        event_id=eid,
        tenant_id="t",
        ts=ts,
        type=etype,
        account_id=acct,
        session_id=eid,
        device_id=device,
        ip="1.1.1.1",
        email=email,
        phone=phone,
        payment_instrument_hash=pay,
        payload=payload or {},
    )


def test_shared_device_cluster_size_and_phone_multi_hop():
    """Two accounts share device → cluster ≥2; third via phone hop → multi-hop ≥3."""
    now = datetime(2026, 8, 5, 12, 0, tzinfo=timezone.utc)
    events = [
        _e("1", "a1", device="devA", phone="555-1111", email="a1@x.com", ts="2026-08-05T10:00:00Z"),
        _e("2", "a2", device="devA", phone="555-2222", email="a2@y.com", ts="2026-08-05T10:30:00Z"),
        _e("3", "a3", device="devB", phone="555-2222", email="a3@z.com", ts="2026-08-05T11:00:00Z"),
    ]
    feats = cluster_features(events, "a1", now)
    assert feats["graph_cluster_size"] >= 2
    assert feats["graph_multi_hop_accounts"] >= 3


def test_common_email_domain_does_not_inflate_cluster():
    """Many @gmail.com accounts do not form one cluster via domain alone; rare device still links."""
    now = datetime(2026, 8, 5, 12, 0, tzinfo=timezone.utc)
    # 8 accounts share @gmail.com only (distinct devices/phones) → no domain edges (n > RARE_MAX)
    gmail_events = [
        _e(
            f"g{i}",
            f"g{i}",
            device=f"devG{i}",
            phone=f"555-100{i}",
            email=f"user{i}@gmail.com",
            ts="2026-08-05T10:00:00Z",
        )
        for i in range(8)
    ]
    feats = cluster_features(gmail_events, "g0", now)
    assert feats["graph_cluster_size"] == 1.0

    # Two accounts share a rare device → still cluster
    rare = [
        _e("d1", "r1", device="rareDev", email="a@other.com", ts="2026-08-05T10:00:00Z"),
        _e("d2", "r2", device="rareDev", email="b@else.com", ts="2026-08-05T10:30:00Z"),
    ]
    feats_dev = cluster_features(rare, "r1", now)
    assert feats_dev["graph_cluster_size"] >= 2


def test_snapshot_exposes_graph_keys():
    store = FeatureStore()
    store.observe(_e("1", "a1", device="devA", ts="2026-08-05T10:00:00Z"))
    store.observe(_e("2", "a2", device="devA", ts="2026-08-05T10:30:00Z"))
    cur = _e(
        "3",
        "a1",
        device="devA",
        etype=EventType.redeem,
        ts="2026-08-05T12:00:00Z",
        payload={"reward_id": "r", "points": 1, "offer_ids": [], "channel": "app"},
    )
    store.observe(cur)
    snap = store.snapshot(cur)
    assert snap["graph_cluster_size"] >= 2
    assert "graph_multi_hop_accounts" in snap
    assert "graph_age_diversity_hours" in snap
    assert "graph_shared_attr_rarity" in snap
    # Phase 1 counters kept
    assert snap["accounts_on_device_24h"] >= 2
