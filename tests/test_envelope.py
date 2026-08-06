"""Unified decision envelope — economics never denies orders."""

from loyalty_abuse.envelope import build_unified_decision
from loyalty_abuse.features import FeatureStore
from loyalty_abuse.schema import EventEnvelope, EventType, SCHEMA_VERSION


def _event(**kwargs):
    base = dict(
        event_id="e1",
        tenant_id="t",
        ts="2026-08-04T12:00:00Z",
        type=EventType.redeem,
        account_id="a1",
        session_id="s",
        device_id="d",
        ip="1.1.1.1",
        payload={},
    )
    base.update(kwargs)
    return EventEnvelope(**base)


def test_unified_embeds_friction_and_economics():
    store = FeatureStore()
    u = build_unified_decision(_event(), store, evaluation_mode="live")
    assert u.friction.score >= 0
    assert u.friction.friction.value in {
        "allow",
        "throttle",
        "soft_challenge",
        "hard_challenge",
        "block",
    }
    assert isinstance(u.economics, dict)
    assert u.economics.get("policy", {}).get("order_decision_untouched") is True
    assert u.evaluation_mode == "live"
    assert u.schema_version == SCHEMA_VERSION


def test_decide_api(tmp_path, monkeypatch):
    monkeypatch.setenv("LOYALTY_ABUSE_AUTH_DISABLED", "false")
    from tests.api_helpers import authed_client

    _app, client, headers, _ = authed_client(tmp_path, db_name="decide.db")
    r = client.post(
        "/v1/decide",
        headers=headers,
        json={
            "event": {
                "event_id": "e1",
                "tenant_id": "t",
                "ts": "2026-08-04T12:00:00Z",
                "type": "redeem",
                "account_id": "a1",
                "session_id": "s",
                "device_id": "d",
                "ip": "1.1.1.1",
                "payload": {"points": 10},
            }
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert "friction" in body and "economics" in body
    assert body["economics"]["policy"]["order_decision_untouched"] is True
