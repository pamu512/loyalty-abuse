"""Shadow evaluate path + chronological dry-run."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from fastapi.testclient import TestClient

from loyalty_abuse_api.app import create_app

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from shadow_dry_run import run_dry_run  # noqa: E402


_EV = {
    "event_id": "evt_shadow_1",
    "tenant_id": "t",
    "ts": "2026-08-04T12:00:00Z",
    "type": "signup",
    "account_id": "a",
    "session_id": "s",
    "device_id": "d",
    "ip": "1.1.1.1",
    "payload": {},
}


def test_shadow_evaluate_logs_recommended_vs_host(tmp_path):
    app = create_app(db_path=tmp_path / "shadow.db")
    client = TestClient(app)
    r = client.post(
        "/v1/shadow/evaluate",
        json={"event": _EV, "host_friction": "allow"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["friction"] in {
        "allow",
        "throttle",
        "soft_challenge",
        "hard_challenge",
        "block",
    }
    assert body["decision_id"]
    assert body["event_id"] == "evt_shadow_1"

    # Enforcing audit path untouched: no decisions row.
    assert app.state.db.list_decisions() == []

    logs = app.state.db.list_shadow_logs()
    assert len(logs) == 1
    row = logs[0]
    assert row["decision_id"] == body["decision_id"]
    assert row["event_id"] == "evt_shadow_1"
    assert row["recommended_friction"] == body["friction"]
    assert row["host_friction"] == "allow"
    logged = json.loads(row["body_json"])
    assert logged["decision_id"] == body["decision_id"]
    assert logged["friction"] == body["friction"]


def test_shadow_evaluate_host_friction_optional(tmp_path):
    app = create_app(db_path=tmp_path / "shadow2.db")
    client = TestClient(app)
    r = client.post("/v1/shadow/evaluate", json={"event": {**_EV, "event_id": "evt_shadow_2"}})
    assert r.status_code == 200
    logs = app.state.db.list_shadow_logs()
    assert len(logs) == 1
    assert logs[0]["host_friction"] is None
    assert logs[0]["recommended_friction"] == r.json()["friction"]


def test_live_evaluate_does_not_write_shadow_logs(tmp_path):
    app = create_app(db_path=tmp_path / "live.db")
    client = TestClient(app)
    r = client.post("/v1/evaluate", json={"event": {**_EV, "event_id": "evt_live_1"}})
    assert r.status_code == 200
    assert len(app.state.db.list_decisions()) == 1
    assert app.state.db.list_shadow_logs() == []


def test_shadow_dry_run_emits_metrics_json(tmp_path):
    out = tmp_path / "shadow_dry_run.json"
    report = run_dry_run(n=40, seed=42, days=5, out=out)
    assert out.is_file()
    on_disk = json.loads(out.read_text())
    assert on_disk == report
    assert report["n"] == 40
    assert "precision" in report
    assert "recall" in report
    assert "insult_proxy" in report
    assert 0.0 <= report["precision"] <= 1.0
    assert 0.0 <= report["recall"] <= 1.0
    assert 0.0 <= report["insult_proxy"] <= 1.0
    assert report["days"] == 5
    assert "by_day" in report
    assert len(report["by_day"]) == 5
