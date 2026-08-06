from loyalty_abuse.calibration import load_calibration
from loyalty_abuse.economics import liability_usd, expected_costs
from loyalty_abuse.schema import EventEnvelope, EventType, FrictionAction


def test_liability_sums_payload():
    e = EventEnvelope(
        event_id="e", tenant_id="t", ts="2026-08-05T00:00:00Z",
        type=EventType.redeem, account_id="a", session_id="s",
        device_id="d", ip="1.1.1.1",
        payload={
            "points_liability_usd": 10.0,
            "discount_usd": 2.5,
            "referral_bonus_usd": 1.5,
            "reward_id": "r",
            "points": 1,
            "offer_ids": [],
            "channel": "app",
        },
    )
    assert liability_usd(e) == 14.0


def test_missing_money_is_zero():
    e = EventEnvelope(
        event_id="e", tenant_id="t", ts="2026-08-05T00:00:00Z",
        type=EventType.redeem, account_id="a", session_id="s",
        device_id="d", ip="1.1.1.1",
        payload={"reward_id": "r", "points": 1, "offer_ids": [], "channel": "app"},
    )
    assert liability_usd(e) == 0.0


def test_evaluate_sets_expected_fields():
    from loyalty_abuse import evaluate
    from loyalty_abuse.features import FeatureStore

    store = FeatureStore()
    base = dict(tenant_id="t", account_id="a1", session_id="s", ip="1.1.1.1", payload={})
    store.observe(
        EventEnvelope(
            event_id="s1", ts="2026-08-04T10:00:00Z", type=EventType.signup, device_id="old", **base
        )
    )
    store.observe(
        EventEnvelope(
            event_id="l1",
            ts="2026-08-04T12:00:00Z",
            type=EventType.login,
            device_id="new",
            email=None,
            phone=None,
            payment_instrument_hash=None,
            tenant_id="t",
            account_id="a1",
            session_id="s",
            ip="9.9.9.9",
            payload={"success": True, "new_device": True, "geo": "XX"},
        )
    )
    store.observe(
        EventEnvelope(
            event_id="p1",
            ts="2026-08-04T12:01:00Z",
            type=EventType.profile_update,
            device_id="new",
            tenant_id="t",
            account_id="a1",
            session_id="s",
            ip="9.9.9.9",
            payload={"fields_changed": ["email"]},
        )
    )
    e = EventEnvelope(
        event_id="r1",
        ts="2026-08-04T12:02:00Z",
        type=EventType.redeem,
        device_id="new",
        tenant_id="t",
        account_id="a1",
        session_id="s",
        ip="9.9.9.9",
        payload={
            "reward_id": "r",
            "points": 50,
            "offer_ids": [],
            "channel": "app",
            "points_liability_usd": 20.0,
        },
    )
    d = evaluate(e, store)
    assert d.policy_version == "friction_v2_2"
    assert d.schema_version == 2
    assert d.friction != FrictionAction.allow
    assert d.score > 0
    liab = liability_usd(e)
    assert liab == 20.0
    assert 0.0 <= d.p_abuse <= 1.0
    exp_loss, exp_insult = expected_costs(
        liab, d.p_abuse, d.friction, cost=load_calibration().get("cost")
    )
    assert d.expected_loss_usd == exp_loss
    assert d.expected_insult_usd == exp_insult
    assert exp_loss > 0.0
    assert exp_insult > 0.0


def test_expected_costs_formula():
    loss, insult = expected_costs(20.0, 0.5, FrictionAction.allow)
    # C_fn=1.0 * 20 * 0.5 * miss_fraction[allow]=1.0 → 10.0; C_fp[allow]=0.0
    assert loss == 10.0
    assert insult == 0.0
    _, insult_block = expected_costs(20.0, 0.5, FrictionAction.block)
    assert insult_block == 1.5
