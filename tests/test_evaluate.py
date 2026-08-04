import json
from pathlib import Path

import pytest

from loyalty_abuse import evaluate
from loyalty_abuse.features import FeatureStore
from loyalty_abuse.schema import EventEnvelope, EventType, FrictionAction

GOLDEN = json.loads((Path(__file__).parent / "fixtures" / "golden_tiers.json").read_text())


def test_clean_redeem_allows():
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
        EventEnvelope(
            event_id="r1",
            tenant_id="t",
            ts="2026-08-04T12:00:00Z",
            type=EventType.redeem,
            account_id="a",
            session_id="s",
            device_id="d",
            ip="1.1.1.1",
            payload={"reward_id": "r", "points": 10, "offer_ids": ["one"], "channel": "app"},
        ),
        store,
    )
    assert d.friction == FrictionAction.allow
    assert d.score < 25
    assert isinstance(d.reasons, list)


def test_ato_forces_hard_floor():
    store = FeatureStore()
    base = dict(tenant_id="t", account_id="a1", session_id="s", ip="1.1.1.1", payload={})
    store.observe(EventEnvelope(event_id="s1", ts="2026-08-04T10:00:00Z", type=EventType.signup, device_id="old", **base))
    store.observe(
        EventEnvelope(
            event_id="l1",
            ts="2026-08-04T12:00:00Z",
            type=EventType.login,
            device_id="new",
            email=None,
            phone=None,
            payment_instrument_hash=None,
            tenant_id="t",
            account_id="a1",
            session_id="s",
            ip="9.9.9.9",
            payload={"success": True, "new_device": True, "geo": "XX"},
        )
    )
    store.observe(
        EventEnvelope(
            event_id="p1",
            ts="2026-08-04T12:01:00Z",
            type=EventType.profile_update,
            device_id="new",
            tenant_id="t",
            account_id="a1",
            session_id="s",
            ip="9.9.9.9",
            payload={"fields_changed": ["email"]},
        )
    )
    d = evaluate(
        EventEnvelope(
            event_id="r1",
            ts="2026-08-04T12:02:00Z",
            type=EventType.redeem,
            device_id="new",
            tenant_id="t",
            account_id="a1",
            session_id="s",
            ip="9.9.9.9",
            payload={"reward_id": "r", "points": 50, "offer_ids": [], "channel": "app"},
        ),
        store,
    )
    assert d.friction in {FrictionAction.hard_challenge, FrictionAction.block}
    assert "ato.login_profile_redeem_chain" in d.reasons


@pytest.mark.parametrize("case", GOLDEN, ids=[c["name"] for c in GOLDEN])
def test_golden_tiers(case):
    store = FeatureStore()
    events = [EventEnvelope(**e) for e in case["events"]]
    for e in events[:-1]:
        store.observe(e)
    d = evaluate(events[-1], store)
    assert d.friction == FrictionAction(case["expected_friction"])
    assert case["expected_reason_substring"] in " ".join(d.reasons)
