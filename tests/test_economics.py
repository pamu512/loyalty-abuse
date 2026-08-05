from loyalty_abuse.economics import liability_usd, expected_costs
from loyalty_abuse.schema import EventEnvelope, EventType, FrictionAction


def test_liability_sums_payload():
    e = EventEnvelope(
        event_id="e", tenant_id="t", ts="2026-08-05T00:00:00Z",
        type=EventType.redeem, account_id="a", session_id="s",
        device_id="d", ip="1.1.1.1",
        payload={"points_liability_usd": 10.0, "discount_usd": 2.5, "reward_id": "r", "points": 1, "offer_ids": [], "channel": "app"},
    )
    assert liability_usd(e) == 12.5


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
    e = EventEnvelope(
        event_id="r1", tenant_id="t", ts="2026-08-05T12:00:00Z",
        type=EventType.redeem, account_id="a", session_id="s",
        device_id="d", ip="1.1.1.1",
        payload={"reward_id": "r", "points": 1, "offer_ids": [], "channel": "app", "points_liability_usd": 20.0},
    )
    d = evaluate(e, store)
    assert d.policy_version == "friction_v2_0"
    assert d.schema_version == 2
    assert d.expected_loss_usd is not None
    assert d.expected_insult_usd is not None
    assert d.expected_insult_usd >= 0.0


def test_expected_costs_formula():
    loss, insult = expected_costs(20.0, 0.5, FrictionAction.allow)
    # C_fn=1.0 * 20 * 0.5 * miss_fraction[allow]=1.0 → 10.0; C_fp[allow]=0.0
    assert loss == 10.0
    assert insult == 0.0
    _, insult_block = expected_costs(20.0, 0.5, FrictionAction.block)
    assert insult_block == 1.5
