"""Ops metrics on GET /v1/analytics/summary."""
from __future__ import annotations

from fastapi.testclient import TestClient

from loyalty_abuse.economics import expected_loss_usd, liability_usd
from loyalty_abuse.schema import EventEnvelope, FrictionAction
from loyalty_abuse_api.analytics import build_ops_metrics
from loyalty_abuse_api.app import create_app
from tests.api_helpers import authed_client
from loyalty_abuse_api.db import Database


_REDEEM = {
    "event_id": "evt_ops_1",
    "tenant_id": "t",
    "ts": "2026-08-04T12:00:00Z",
    "type": "redeem",
    "account_id": "a",
    "session_id": "s",
    "device_id": "d",
    "ip": "1.1.1.1",
    "payload": {
        "reward_id": "r",
        "points": 10,
        "offer_ids": ["one"],
        "channel": "app",
        "points_liability_usd": 20.0,
    },
}


def test_ops_metrics_empty(tmp_path):
    client = TestClient(create_app(db_path=tmp_path / "ops.db"))
    r = client.get("/v1/analytics/summary")
    assert r.status_code == 200
    body = r.json()
    assert "insult_proxy" in body
    assert "expected_loss" in body
    assert "intel_calls" in body
    assert "challenge_conversion" in body
    assert body["intel_calls"]["success_rate"] is None
    assert body["intel_calls"]["p50_latency_ms"] is None
    assert body["challenge_conversion"] is None
    assert body["floor_raised_count"] == 0
    assert body["floor_raised_rate"] == 0.0


def test_insult_proxy_allow_labeled_shadow(tmp_path):
    app = create_app(db_path=tmp_path / "ops.db")
    client = TestClient(app)
    # host allow + recommended hard_challenge → insult
    r = client.post(
        "/v1/shadow/evaluate",
        json={
            "event": {**_REDEEM, "event_id": "sh1", "account_id": "a1"},
            "host_friction": "allow",
        },
    )
    assert r.status_code == 200
    # force another allow-labeled with allow recommend via signup
    r2 = client.post(
        "/v1/shadow/evaluate",
        json={
            "event": {
                "event_id": "sh2",
                "tenant_id": "t",
                "ts": "2026-08-04T12:01:00Z",
                "type": "signup",
                "account_id": "a2",
                "session_id": "s2",
                "device_id": "d2",
                "ip": "2.2.2.2",
                "payload": {},
            },
            "host_friction": "allow",
        },
    )
    assert r2.status_code == 200
    summary = client.get("/v1/analytics/summary").json()
    assert 0.0 <= summary["insult_proxy"] <= 1.0
    # at least one of two allow-labeled shadows may be hard_challenge+
    hard_plus = {"hard_challenge", "block"}
    logs = app.state.db.list_shadow_logs()
    allow_labeled = [x for x in logs if x["host_friction"] == "allow"]
    assert len(allow_labeled) == 2
    expected = sum(1 for x in allow_labeled if x["recommended_friction"] in hard_plus) / 2
    assert summary["insult_proxy"] == expected


def test_insult_proxy_falls_back_to_friction_mix(tmp_path):
    client = TestClient(create_app(db_path=tmp_path / "ops.db"))
    r = client.post("/v1/evaluate", json={"event": _REDEEM})
    assert r.status_code == 200
    friction = r.json()["friction"]
    summary = client.get("/v1/analytics/summary").json()
    hard_plus = friction in {"hard_challenge", "block"}
    assert summary["insult_proxy"] == (1.0 if hard_plus else 0.0)


def test_intel_calls_and_challenge_conversion(tmp_path):
    db = Database(tmp_path / "ops.db")
    db.log_intel_call(
        event_id="e1", vendor="incognia", success=True, latency_ms=10, source="fixture"
    )
    db.log_intel_call(
        event_id="e2", vendor="incognia", success=False, latency_ms=40, source="fixture"
    )
    db.log_intel_call(
        event_id="e3", vendor="incognia", success=True, latency_ms=20, source="fixture"
    )
    db.save_challenge_outcome(
        decision_id="d1", outcome="passed", ts="2026-08-04T12:00:00Z"
    )
    db.save_challenge_outcome(
        decision_id="d2", outcome="failed", ts="2026-08-04T12:01:00Z"
    )
    db.save_challenge_outcome(
        decision_id="d3", outcome="abandoned", ts="2026-08-04T12:02:00Z"
    )
    db.save_challenge_outcome(
        decision_id="d4", outcome="passed", ts="2026-08-04T12:03:00Z"
    )
    app = create_app(db_path=tmp_path / "ops.db")
    # reuse same db file
    app.state.db = db
    client = TestClient(app)
    summary = client.get("/v1/analytics/summary").json()
    assert summary["intel_calls"]["success_rate"] == 2 / 3
    assert summary["intel_calls"]["p50_latency_ms"] == 20
    assert summary["challenge_conversion"] == 2 / 4


def test_expected_loss_vs_allow_all(tmp_path):
    client = TestClient(create_app(db_path=tmp_path / "ops.db"))
    r = client.post("/v1/evaluate", json={"event": _REDEEM})
    assert r.status_code == 200
    decision = r.json()
    summary = client.get("/v1/analytics/summary").json()
    el = summary["expected_loss"]
    assert el["policy_sum"] == decision["expected_loss_usd"]
    event = EventEnvelope.model_validate(_REDEEM)
    allow_all = expected_loss_usd(
        liability_usd(event), decision["p_abuse"], FrictionAction.allow
    )
    assert el["allow_all_sum"] == allow_all
    assert el["allow_all_sum"] >= el["policy_sum"]


def test_floor_raised_metrics():
    metrics = build_ops_metrics(
        decisions=[
            {
                "friction": "soft_challenge",
                "score": 22,
                "reasons": ["floor.soft.slow_multi"],
                "features_snapshot": {"band_friction": "allow"},
            },
            {
                "friction": "allow",
                "score": 10,
                "reasons": [],
                "features_snapshot": {"band_friction": "allow"},
            },
        ]
    )
    assert metrics["floor_raised_count"] == 1
    assert metrics["floor_raised_rate"] == 0.5
