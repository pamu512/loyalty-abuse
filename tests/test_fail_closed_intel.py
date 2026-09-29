"""Live-shaped redeem/dispatch without intel credentials must not score clean."""

from __future__ import annotations

_INTEL_ENV = (
    "INCOGNIA_CLIENT_ID",
    "INCOGNIA_CLIENT_SECRET",
    "INCOGNIA_POLICY_ID",
    "CONSORTIUM_API_KEY",
    "CONSORTIUM_FEED_URL",
)

_LIVE_REDEEM = {
    "event_id": "r_live_fc_1",
    "tenant_id": "t",
    "ts": "2026-08-04T12:00:00Z",
    "type": "redeem",
    "account_id": "a1",
    "session_id": "s",
    "device_id": "d",
    "ip": "1.1.1.1",
    "payload": {
        "reward_id": "r",
        "points": 10,
        "offer_ids": ["one"],
        "channel": "app",
    },
}


def test_live_shaped_decide_redeem_without_credentials_not_clean(tmp_path, monkeypatch):
    for key in _INTEL_ENV:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.delenv("INCOGNIA_REQUIRED_DEFAULT", raising=False)

    from tests.api_helpers import authed_client

    _app, client, headers, _ = authed_client(tmp_path, db_name="fail_closed.db")
    r = client.post(
        "/v1/decide",
        headers=headers,
        json={"event": _LIVE_REDEEM, "evaluation_mode": "live"},
    )
    assert r.status_code == 200
    body = r.json()
    friction = body["friction"]
    action = friction["friction"]
    reasons = friction["reasons"]
    snap = friction["features_snapshot"]

    assert action != "allow"
    assert action in {"hard_challenge", "block"}
    assert "intel.consortium_missing_feed" in reasons
    assert snap.get("force_hard_floor") is True
    consortium = snap.get("consortium") or {}
    assert consortium.get("status") == "not_configured"
    assert consortium.get("reason") == "missing_feed"
    assert consortium.get("blocked") is True
    # Nested scores may be empty; that must not be treated as a clean hit.
    assert consortium != {}
