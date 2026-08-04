from fastapi.testclient import TestClient

from loyalty_abuse import evaluate
from loyalty_abuse.features import FeatureStore
from loyalty_abuse.schema import EventEnvelope, EventType
from loyalty_abuse_api.app import create_app


def test_evaluate_persists_before_200(tmp_path):
    app = create_app(db_path=tmp_path / "t.db")
    client = TestClient(app)
    ev = {
        "event_id": "evt_api_1",
        "tenant_id": "t",
        "ts": "2026-08-04T12:00:00Z",
        "type": "signup",
        "account_id": "a",
        "session_id": "s",
        "device_id": "d",
        "ip": "1.1.1.1",
        "payload": {},
    }
    r = client.post("/v1/events", json={**ev, "evaluate": True})
    assert r.status_code == 200
    body = r.json()
    assert body["friction"] in {"allow", "throttle", "soft_challenge", "hard_challenge", "block"}
    d = client.get(f"/v1/decisions/{body['decision_id']}")
    assert d.status_code == 200
    assert d.json()["event_id"] == "evt_api_1"


def test_audit_failure_returns_503(tmp_path, monkeypatch):
    app = create_app(db_path=tmp_path / "t.db")
    client = TestClient(app)

    def boom(*_a, **_k):
        raise RuntimeError("disk full")

    monkeypatch.setattr(app.state.db, "save_decision", boom)
    ev = {
        "event_id": "evt_api_2",
        "tenant_id": "t",
        "ts": "2026-08-04T12:00:00Z",
        "type": "signup",
        "account_id": "a",
        "session_id": "s",
        "device_id": "d",
        "ip": "1.1.1.1",
        "payload": {},
    }
    r = client.post("/v1/evaluate", json={"event": ev})
    assert r.status_code == 503


def test_observe_order_accounts_on_device_parity(tmp_path):
    """Priors must be observed; scored event must not be double-observed before evaluate."""
    s1 = EventEnvelope(
        event_id="s1",
        tenant_id="t",
        ts="2026-08-04T12:00:00Z",
        type=EventType.signup,
        account_id="a1",
        session_id="s1",
        device_id="shared",
        ip="1.1.1.1",
        payload={},
    )
    s2 = EventEnvelope(
        event_id="s2",
        tenant_id="t",
        ts="2026-08-04T12:01:00Z",
        type=EventType.signup,
        account_id="a2",
        session_id="s2",
        device_id="shared",
        ip="1.1.1.1",
        payload={},
    )
    redeem = EventEnvelope(
        event_id="r1",
        tenant_id="t",
        ts="2026-08-04T12:02:00Z",
        type=EventType.redeem,
        account_id="a2",
        session_id="s2",
        device_id="shared",
        ip="1.1.1.1",
        payload={"reward_id": "r", "points": 10, "offer_ids": ["one"], "channel": "app"},
    )

    store = FeatureStore()
    store.observe(s1)
    store.observe(s2)
    lib_d = evaluate(redeem, store)

    app = create_app(db_path=tmp_path / "parity.db")
    client = TestClient(app)
    assert client.post("/v1/events", json={**s1.model_dump(mode="json"), "evaluate": False}).status_code == 200
    assert client.post("/v1/events", json={**s2.model_dump(mode="json"), "evaluate": False}).status_code == 200
    r = client.post("/v1/evaluate", json={"event": redeem.model_dump(mode="json")})
    assert r.status_code == 200
    api_snap = r.json()["features_snapshot"]
    assert api_snap["accounts_on_device_24h"] == lib_d.features_snapshot["accounts_on_device_24h"] == 2


def test_library_http_score_parity(tmp_path):
    events = [
        EventEnvelope(
            event_id="s1",
            tenant_id="t",
            ts="2026-08-04T12:00:00Z",
            type=EventType.signup,
            account_id="a1",
            session_id="s1",
            device_id="devX",
            ip="1.1.1.1",
            payload={},
        ),
        EventEnvelope(
            event_id="s2",
            tenant_id="t",
            ts="2026-08-04T12:01:00Z",
            type=EventType.signup,
            account_id="a2",
            session_id="s2",
            device_id="devX",
            ip="1.1.1.1",
            payload={},
        ),
        EventEnvelope(
            event_id="s3",
            tenant_id="t",
            ts="2026-08-04T12:02:00Z",
            type=EventType.signup,
            account_id="a3",
            session_id="s3",
            device_id="devX",
            ip="1.1.1.1",
            payload={},
        ),
        EventEnvelope(
            event_id="r1",
            tenant_id="t",
            ts="2026-08-04T12:03:00Z",
            type=EventType.redeem,
            account_id="a3",
            session_id="s3",
            device_id="devX",
            ip="1.1.1.1",
            payload={"reward_id": "r", "points": 10, "offer_ids": ["one"], "channel": "app"},
        ),
    ]

    store = FeatureStore()
    for e in events[:-1]:
        store.observe(e)
    lib_d = evaluate(events[-1], store)

    app = create_app(db_path=tmp_path / "score_parity.db")
    client = TestClient(app)
    for e in events[:-1]:
        assert client.post("/v1/events", json={**e.model_dump(mode="json"), "evaluate": False}).status_code == 200
    r = client.post("/v1/evaluate", json={"event": events[-1].model_dump(mode="json")})
    assert r.status_code == 200
    api = r.json()
    assert api["score"] == lib_d.score
    assert api["friction"] == lib_d.friction.value
    assert sorted(api["reasons"]) == sorted(lib_d.reasons)
