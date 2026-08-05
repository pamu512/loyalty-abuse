"""API Incognia enrich + fail-closed / fail-open (fixtures / monkeypatch only)."""

from __future__ import annotations

from adapters.incognia.normalize import IncogniaSignals, normalize_assessment
from fastapi.testclient import TestClient

from loyalty_abuse_api.app import create_app


def _redeem_event(*, payload: dict, event_id: str = "r_intel_1") -> dict:
    return {
        "event_id": event_id,
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
            **payload,
        },
    }


def _unavailable_signals() -> IncogniaSignals:
    return normalize_assessment({}, source="unavailable")


def _high_risk_signals() -> IncogniaSignals:
    return normalize_assessment(
        {
            "id": "fix-high",
            "risk_assessment": "high_risk",
            "evidence": {
                "device_integrity": {
                    "probable_root": True,
                    "emulator": False,
                    "gps_spoofing": False,
                },
            },
        },
        source="fixture",
    )


def test_evaluate_without_token_does_not_call_fetch(tmp_path, monkeypatch):
    app = create_app(db_path=tmp_path / "t.db")
    client = TestClient(app)
    calls: list = []

    def boom(**_kw):
        calls.append(1)
        raise AssertionError("fetch_signals must not be called without token")

    monkeypatch.setattr("adapters.incognia.fetch_signals", boom)
    monkeypatch.setattr("loyalty_abuse_api.app.fetch_signals", boom, raising=False)

    r = client.post("/v1/evaluate", json={"event": _redeem_event(payload={})})
    assert r.status_code == 200
    assert calls == []


def test_enrich_merges_signals_and_logs_intel_call(tmp_path, monkeypatch):
    app = create_app(db_path=tmp_path / "t.db")
    client = TestClient(app)
    seen: dict = {}

    def fake_fetch(**kw):
        seen.update(kw)
        return _high_risk_signals()

    monkeypatch.setattr("adapters.incognia.fetch_signals", fake_fetch)
    monkeypatch.setattr("loyalty_abuse_api.app.fetch_signals", fake_fetch, raising=False)

    r = client.post(
        "/v1/evaluate",
        json={
            "event": _redeem_event(
                payload={"request_token": "tok-abc", "incognia_required": False}
            )
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert seen.get("request_token") == "tok-abc"
    assert seen.get("account_id") == "a"
    assert seen.get("event_type") == "redeem"
    assert "intel.incognia_high_risk" in body["reasons"]
    assert body["friction"] in {"hard_challenge", "block"}
    assert body["features_snapshot"].get("device_intel", {}).get("risk_assessment") == "high_risk"

    rows = app.state.db.list_intel_calls()
    assert len(rows) == 1
    assert rows[0]["event_id"] == "r_intel_1"
    assert rows[0]["success"] is True
    assert isinstance(rows[0]["latency_ms"], int)
    assert rows[0]["latency_ms"] >= 0


def test_incognia_request_token_alias(tmp_path, monkeypatch):
    app = create_app(db_path=tmp_path / "t.db")
    client = TestClient(app)
    seen: list[str] = []

    def fake_fetch(**kw):
        seen.append(kw["request_token"])
        return _high_risk_signals()

    monkeypatch.setattr("adapters.incognia.fetch_signals", fake_fetch)
    monkeypatch.setattr("loyalty_abuse_api.app.fetch_signals", fake_fetch, raising=False)

    r = client.post(
        "/v1/evaluate",
        json={"event": _redeem_event(payload={"incognia_request_token": "alias-tok"})},
    )
    assert r.status_code == 200
    assert seen == ["alias-tok"]


def test_fail_closed_unavailable_required_redeem(tmp_path, monkeypatch):
    app = create_app(db_path=tmp_path / "t.db")
    client = TestClient(app)
    monkeypatch.setattr(
        "adapters.incognia.fetch_signals",
        lambda **_kw: _unavailable_signals(),
    )
    monkeypatch.setattr(
        "loyalty_abuse_api.app.fetch_signals",
        lambda **_kw: _unavailable_signals(),
        raising=False,
    )

    r = client.post(
        "/v1/evaluate",
        json={
            "event": _redeem_event(
                payload={"request_token": "tok", "incognia_required": True}
            )
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["friction"] in {"hard_challenge", "block"}
    assert "intel.incognia_unavailable" in body["reasons"]
    assert "intel.incognia_high_risk" not in body["reasons"]
    assert body["features_snapshot"].get("force_hard_floor") is True
    assert body["features_snapshot"].get("device_intel_force_block") is True

    rows = app.state.db.list_intel_calls()
    assert len(rows) == 1
    assert rows[0]["success"] is False


def test_fail_closed_unavailable_required_checkout(tmp_path, monkeypatch):
    app = create_app(db_path=tmp_path / "t.db")
    client = TestClient(app)
    monkeypatch.setattr(
        "adapters.incognia.fetch_signals",
        lambda **_kw: _unavailable_signals(),
    )
    monkeypatch.setattr(
        "loyalty_abuse_api.app.fetch_signals",
        lambda **_kw: _unavailable_signals(),
        raising=False,
    )
    ev = _redeem_event(
        payload={"request_token": "tok", "incognia_required": True},
        event_id="c_intel_1",
    )
    ev["type"] = "checkout"

    r = client.post("/v1/evaluate", json={"event": ev})
    assert r.status_code == 200
    body = r.json()
    assert body["friction"] in {"hard_challenge", "block"}
    assert "intel.incognia_unavailable" in body["reasons"]


def test_fail_open_unavailable_not_required(tmp_path, monkeypatch):
    app = create_app(db_path=tmp_path / "t.db")
    client = TestClient(app)
    monkeypatch.delenv("INCOGNIA_REQUIRED_DEFAULT", raising=False)
    monkeypatch.setattr(
        "adapters.incognia.fetch_signals",
        lambda **_kw: _unavailable_signals(),
    )
    monkeypatch.setattr(
        "loyalty_abuse_api.app.fetch_signals",
        lambda **_kw: _unavailable_signals(),
        raising=False,
    )

    r = client.post(
        "/v1/evaluate",
        json={"event": _redeem_event(payload={"request_token": "tok"})},
    )
    assert r.status_code == 200
    body = r.json()
    assert "intel.incognia_unavailable" in body["reasons"]
    assert body["features_snapshot"].get("device_intel_force_block") is not True
    # Clean redeem without force-block stays allow (fail-open).
    assert body["friction"] == "allow"


def test_required_default_env_fail_closed(tmp_path, monkeypatch):
    app = create_app(db_path=tmp_path / "t.db")
    client = TestClient(app)
    monkeypatch.setenv("INCOGNIA_REQUIRED_DEFAULT", "true")
    monkeypatch.setattr(
        "adapters.incognia.fetch_signals",
        lambda **_kw: _unavailable_signals(),
    )
    monkeypatch.setattr(
        "loyalty_abuse_api.app.fetch_signals",
        lambda **_kw: _unavailable_signals(),
        raising=False,
    )

    r = client.post(
        "/v1/evaluate",
        json={"event": _redeem_event(payload={"request_token": "tok"})},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["friction"] in {"hard_challenge", "block"}
    assert "intel.incognia_unavailable" in body["reasons"]
