"""P1 auth / tenant / rate-limit / export contracts."""

import os

from fastapi.testclient import TestClient

from loyalty_abuse_api.app import create_app
from tests.api_helpers import authed_client


def test_evaluate_requires_bearer(tmp_path, monkeypatch):
    monkeypatch.delenv("LOYALTY_ABUSE_AUTH_DISABLED", raising=False)
    monkeypatch.setenv("LOYALTY_ABUSE_AUTH_DISABLED", "false")
    app = create_app(db_path=tmp_path / "auth.db")
    client = TestClient(app)
    r = client.post(
        "/v1/evaluate",
        json={
            "event": {
                "event_id": "e1",
                "tenant_id": "t",
                "ts": "2026-08-04T12:00:00Z",
                "type": "signup",
                "account_id": "a",
                "session_id": "s",
                "device_id": "d",
                "ip": "1.1.1.1",
                "payload": {},
            }
        },
    )
    assert r.status_code == 401


def test_cross_tenant_forbidden(tmp_path, monkeypatch):
    monkeypatch.setenv("LOYALTY_ABUSE_AUTH_DISABLED", "false")
    app, client, headers, _ = authed_client(tmp_path, tenant_id="t1", db_name="x.db")
    r = client.post(
        "/v1/evaluate",
        headers=headers,
        json={
            "event": {
                "event_id": "e1",
                "tenant_id": "other",
                "ts": "2026-08-04T12:00:00Z",
                "type": "signup",
                "account_id": "a",
                "session_id": "s",
                "device_id": "d",
                "ip": "1.1.1.1",
                "payload": {},
            }
        },
    )
    assert r.status_code == 403


def test_rate_limit_429(tmp_path, monkeypatch):
    monkeypatch.setenv("LOYALTY_ABUSE_AUTH_DISABLED", "false")
    app, client, headers, _ = authed_client(
        tmp_path, tenant_id="t", db_name="rl.db", rpm=2
    )
    body = {
        "event": {
            "event_id": "e0",
            "tenant_id": "t",
            "ts": "2026-08-04T12:00:00Z",
            "type": "signup",
            "account_id": "a",
            "session_id": "s",
            "device_id": "d",
            "ip": "1.1.1.1",
            "payload": {},
        }
    }
    assert client.post("/v1/evaluate", headers=headers, json=body).status_code == 200
    body["event"]["event_id"] = "e1"
    assert client.post("/v1/evaluate", headers=headers, json=body).status_code == 200
    body["event"]["event_id"] = "e2"
    r = client.post("/v1/evaluate", headers=headers, json=body)
    assert r.status_code == 429
    assert "Retry-After" in r.headers


def test_export_ndjson(tmp_path, monkeypatch):
    monkeypatch.setenv("LOYALTY_ABUSE_AUTH_DISABLED", "false")
    app, client, headers, _ = authed_client(tmp_path, tenant_id="t", db_name="ex.db")
    client.post(
        "/v1/evaluate",
        headers=headers,
        json={
            "event": {
                "event_id": "e1",
                "tenant_id": "t",
                "ts": "2026-08-04T12:00:00Z",
                "type": "signup",
                "account_id": "a",
                "session_id": "s",
                "device_id": "d",
                "ip": "1.1.1.1",
                "payload": {},
            }
        },
    )
    r = client.get("/v1/export/decisions", headers=headers)
    assert r.status_code == 200
    assert "application/x-ndjson" in r.headers["content-type"]
    lines = [ln for ln in r.text.strip().split("\n") if ln]
    assert len(lines) == 1
    assert "decision_id" in lines[0]


def test_bootstrap_admin_mints_key(tmp_path, monkeypatch):
    monkeypatch.setenv("LOYALTY_ABUSE_AUTH_DISABLED", "false")
    monkeypatch.setenv("LOYALTY_ABUSE_BOOTSTRAP_ADMIN_KEY", "admin-secret-test")
    app = create_app(db_path=tmp_path / "adm.db")
    client = TestClient(app)
    r = client.post(
        "/v1/admin/keys",
        headers={"Authorization": "Bearer admin-secret-test"},
        json={"tenant_id": "acme", "name": "prod", "rpm": 60},
    )
    assert r.status_code == 200
    assert r.json()["api_key"].startswith("la_")
    assert r.json()["tenant_id"] == "acme"
