import json
from pathlib import Path

from loyalty_abuse.schema import Decision, EventEnvelope, FrictionAction, SCHEMA_VERSION

ROOT = Path(__file__).resolve().parents[1] / "contracts"

EVENT_EXAMPLE = {
    "event_id": "evt_contract_1",
    "tenant_id": "t1",
    "ts": "2026-08-04T00:00:00Z",
    "type": "redeem",
    "account_id": "acct_1",
    "session_id": "sess_1",
    "device_id": "dev_1",
    "ip": "1.2.3.4",
    "payload": {"reward_id": "r1", "points": 100, "offer_ids": ["o1"], "channel": "app"},
}

DECISION_EXAMPLE = {
    "decision_id": "dec_contract_1",
    "event_id": "evt_contract_1",
    "score": 72,
    "friction": "hard_challenge",
    "reasons": ["ato.login_profile_redeem_chain"],
    "typology_breakdown": [
        {"id": "ato_redeem", "points": 40, "reasons": ["ato.login_profile_redeem_chain"]},
    ],
    "features_snapshot": {"ato_chain": True},
    "policy_version": "friction_v2_0",
    "schema_version": SCHEMA_VERSION,
    "expected_loss_usd": 0.0,
    "expected_insult_usd": 0.0,
    "p_abuse": 0.0,
}

EVALUATE_BY_ID = {"event_id": "evt_contract_1"}
EVALUATE_INLINE = {"event": EVENT_EXAMPLE}
EVALUATE_WITH_FLAG = {"event": EVENT_EXAMPLE, "evaluate": True}


def test_contract_files_exist():
    for name in ("event-envelope.schema.json", "evaluate-request.schema.json", "decision.schema.json"):
        assert (ROOT / name).is_file()


def test_event_schema_lists_required():
    schema = json.loads((ROOT / "event-envelope.schema.json").read_text())
    for key in ("event_id", "tenant_id", "ts", "type", "account_id", "device_id", "ip"):
        assert key in schema.get("required", []) or key in schema.get("properties", {})


def test_decision_schema_lists_required():
    schema = json.loads((ROOT / "decision.schema.json").read_text())
    for key in ("decision_id", "event_id", "score", "friction", "reasons", "typology_breakdown"):
        assert key in schema.get("required", []) or key in schema.get("properties", {})


def test_evaluate_request_schema_shape():
    schema = json.loads((ROOT / "evaluate-request.schema.json").read_text())
    assert "oneOf" in schema
    variants = schema["oneOf"]
    assert any("event_id" in v.get("properties", {}) for v in variants)
    assert any("event" in v.get("properties", {}) for v in variants)


def test_event_envelope_example_roundtrip():
    assert EventEnvelope.model_validate(EVENT_EXAMPLE).event_id == "evt_contract_1"


def test_decision_example_roundtrip():
    d = Decision.model_validate(DECISION_EXAMPLE)
    assert d.friction == FrictionAction.hard_challenge
    assert d.schema_version == SCHEMA_VERSION


def test_evaluate_request_examples_parse_event():
    EventEnvelope.model_validate(EVALUATE_INLINE["event"])
    EventEnvelope.model_validate(EVALUATE_WITH_FLAG["event"])
    assert EVALUATE_BY_ID["event_id"] == "evt_contract_1"


def test_contract_properties_match_pydantic_models():
    for model, name in ((EventEnvelope, "event-envelope.schema.json"), (Decision, "decision.schema.json")):
        pydantic_schema = model.model_json_schema()
        contract = json.loads((ROOT / name).read_text())
        pydantic_props = set(pydantic_schema.get("properties", {}))
        contract_props = set(contract.get("properties", {}))
        assert contract_props <= pydantic_props
        for req in contract.get("required", []):
            assert req in pydantic_schema.get("required", []) or req in pydantic_props
