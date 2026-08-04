from fastapi.testclient import TestClient
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
