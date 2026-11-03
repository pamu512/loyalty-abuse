"""Live-shaped redeem/dispatch without intel credentials must not score clean.

#1.3: synthetic redeem/dispatch fixture (not production evidence) proves
evaluate + multi_gate fail-closed on missing intel/economics feeds.
"""

from __future__ import annotations

import json
from pathlib import Path

from adapters.consortium import OPERATOR_REASON as _OPERATOR_DENY

_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "synthetic_redeem_dispatch.json"

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


def _synthetic_pack() -> dict:
    pack = json.loads(_FIXTURE_PATH.read_text())
    assert pack.get("synthetic") is True
    assert pack.get("production_evidence") is False
    return pack


def test_synthetic_redeem_dispatch_fixture_is_labeled_non_prod():
    pack = _synthetic_pack()
    note = str(pack.get("note") or "")
    assert "SYNTHETIC" in note
    assert "not production evidence" in note.lower()
    event = pack["event"]
    assert event["type"] == "redeem"
    assert event["payload"]["fulfillment"]["kind"] == "dispatch"
    assert pack.get("feed_snapshot") is None


def test_evaluate_synthetic_redeem_missing_intel_fail_closed():
    from adapters.consortium import lookup_badness
    from loyalty_abuse import evaluate
    from loyalty_abuse.features import FeatureStore
    from loyalty_abuse.schema import EventEnvelope

    pack = _synthetic_pack()
    event = EventEnvelope.model_validate(pack["event"])
    payload = dict(event.payload)
    payload["consortium"] = lookup_badness(
        [event.account_id, event.device_id, event.payment_instrument_hash]
    )
    event = event.model_copy(update={"payload": payload})

    decision = evaluate(event, FeatureStore())
    action = decision.friction.value
    assert action != "allow"
    assert action in {"hard_challenge", "block"}
    assert "intel.consortium_missing_feed" in decision.reasons
    assert _OPERATOR_DENY in decision.reasons
    snap = decision.features_snapshot
    assert snap.get("force_hard_floor") is True
    consortium = snap.get("consortium") or {}
    assert consortium.get("status") == "not_configured"
    assert consortium.get("reason") == "missing_feed"
    assert consortium.get("blocked") is True
    assert consortium.get("operator_reason") == _OPERATOR_DENY


def test_multi_gate_synthetic_dispatch_missing_feeds_fail_closed():
    from loyalty_abuse.multi_gate import evaluate_loyalty_economics

    pack = _synthetic_pack()
    out = evaluate_loyalty_economics(
        entity_id=pack["event"]["account_id"],
        feed_snapshot=pack.get("feed_snapshot"),
        program_config=pack.get("program_config"),
        scope=pack.get("scope"),
    )
    assert out["status"] in {"feeds_missing", "not_configured", "missing_feed"}
    assert out["policy"]["order_decision_untouched"] is True
    for name in ("dispatch", "redeem"):
        gate = out["gates"][name]
        assert gate["eligible"] is not True
        assert gate["eligible"] is None
        assert gate["status"] == out["status"]
        assert out["status"] in gate["reasons"]
        joined = " ".join(gate["reasons"]).lower()
        assert "not eligible" in joined or "missing" in joined


def test_decide_synthetic_fixture_without_credentials_not_clean(tmp_path, monkeypatch):
    for key in _INTEL_ENV:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.delenv("INCOGNIA_REQUIRED_DEFAULT", raising=False)

    from tests.api_helpers import authed_client

    pack = _synthetic_pack()
    _app, client, headers, _ = authed_client(tmp_path, db_name="fail_closed_synth.db")
    r = client.post(
        "/v1/decide",
        headers=headers,
        json={
            "event": pack["event"],
            "feed_snapshot": pack.get("feed_snapshot"),
            "program_config": pack.get("program_config"),
            "scope": pack.get("scope"),
            "evaluation_mode": pack.get("evaluation_mode") or "live",
        },
    )
    assert r.status_code == 200
    body = r.json()
    friction = body["friction"]
    action = friction["friction"]
    reasons = friction["reasons"]
    snap = friction["features_snapshot"]
    economics = body["economics"]

    assert action != "allow"
    assert action in {"hard_challenge", "block"}
    assert "intel.consortium_missing_feed" in reasons
    assert _OPERATOR_DENY in reasons
    consortium = snap.get("consortium") or {}
    assert consortium.get("status") == "not_configured"
    assert consortium.get("reason") == "missing_feed"
    assert consortium.get("operator_reason") == _OPERATOR_DENY
    assert economics["status"] in {"feeds_missing", "not_configured", "missing_feed"}
    assert economics["gates"]["dispatch"]["eligible"] is not True
    assert economics["gates"]["redeem"]["eligible"] is not True
    assert economics["status"] in economics["gates"]["dispatch"]["reasons"]
    assert economics["status"] in economics["gates"]["redeem"]["reasons"]
