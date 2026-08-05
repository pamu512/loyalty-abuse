"""Challenge outcome ingest — labels only; never mutates decisions."""
from __future__ import annotations

from fastapi.testclient import TestClient

from loyalty_abuse_api.app import create_app


_EV = {
    "event_id": "evt_chal_1",
    "tenant_id": "t",
    "ts": "2026-08-04T12:00:00Z",
    "type": "redeem",
    "account_id": "a",
    "session_id": "s",
    "device_id": "d",
    "ip": "1.1.1.1",
    "payload": {"reward_id": "r", "points": 10, "offer_ids": ["one"], "channel": "app"},
}


def test_challenge_outcome_round_trip_by_decision_id(tmp_path):
    app = create_app(db_path=tmp_path / "chal.db")
    client = TestClient(app)

    r = client.post("/v1/evaluate", json={"event": _EV})
    assert r.status_code == 200
    decision = r.json()
    decision_id = decision["decision_id"]
    before = client.get(f"/v1/decisions/{decision_id}").json()

    body = {
        "decision_id": decision_id,
        "event_id": "evt_chal_1",
        "outcome": "passed",
        "ts": "2026-08-04T12:05:00Z",
    }
    post = client.post("/v1/challenge_outcomes", json=body)
    assert post.status_code == 200
    assert post.json()["decision_id"] == decision_id
    assert post.json()["outcome"] == "passed"

    rows = app.state.db.list_challenge_outcomes(decision_id=decision_id)
    assert len(rows) == 1
    assert rows[0]["decision_id"] == decision_id
    assert rows[0]["event_id"] == "evt_chal_1"
    assert rows[0]["outcome"] == "passed"
    assert rows[0]["ts"] == "2026-08-04T12:05:00Z"

    after = client.get(f"/v1/decisions/{decision_id}").json()
    assert after == before


def test_challenge_outcome_event_id_optional(tmp_path):
    app = create_app(db_path=tmp_path / "chal2.db")
    client = TestClient(app)
    decision_id = client.post("/v1/evaluate", json={"event": {**_EV, "event_id": "evt_chal_2"}}).json()[
        "decision_id"
    ]
    r = client.post(
        "/v1/challenge_outcomes",
        json={
            "decision_id": decision_id,
            "outcome": "abandoned",
            "ts": "2026-08-04T13:00:00Z",
        },
    )
    assert r.status_code == 200
    rows = app.state.db.list_challenge_outcomes(decision_id=decision_id)
    assert len(rows) == 1
    assert rows[0]["event_id"] is None
    assert rows[0]["outcome"] == "abandoned"


def test_challenge_outcome_rejects_invalid_outcome(tmp_path):
    app = create_app(db_path=tmp_path / "chal3.db")
    client = TestClient(app)
    r = client.post(
        "/v1/challenge_outcomes",
        json={
            "decision_id": "dec_x",
            "outcome": "maybe",
            "ts": "2026-08-04T12:00:00Z",
        },
    )
    assert r.status_code == 422
