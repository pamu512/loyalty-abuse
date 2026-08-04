from loyalty_abuse.schema import Decision, EventEnvelope, FrictionAction, SCHEMA_VERSION


def test_friction_actions_exact_set():
    assert {a.value for a in FrictionAction} == {
        "allow",
        "throttle",
        "soft_challenge",
        "hard_challenge",
        "block",
    }
    assert "review" not in {a.value for a in FrictionAction}


def test_event_envelope_roundtrip():
    e = EventEnvelope(
        event_id="evt_1",
        tenant_id="t1",
        ts="2026-08-04T00:00:00Z",
        type="redeem",
        account_id="acct_1",
        session_id="sess_1",
        device_id="dev_1",
        ip="1.2.3.4",
        payload={"reward_id": "r1", "points": 100, "offer_ids": ["o1"], "channel": "app"},
    )
    data = e.model_dump()
    assert EventEnvelope.model_validate(data).event_id == "evt_1"


def test_decision_requires_reasons_and_breakdown():
    d = Decision(
        decision_id="dec_1",
        event_id="evt_1",
        score=0,
        friction=FrictionAction.allow,
        reasons=[],
        typology_breakdown=[],
        features_snapshot={},
        policy_version="friction_v1",
        schema_version=SCHEMA_VERSION,
    )
    assert d.schema_version == 1
