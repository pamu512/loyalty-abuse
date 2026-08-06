from loyalty_abuse.calibration import load_calibration
from loyalty_abuse.features import FeatureStore
from loyalty_abuse.floors import apply_soft_floors
from loyalty_abuse.schema import EventEnvelope, EventType, FrictionAction, TypologyResult
from loyalty_abuse.score import evaluate


def _stub_scorers(confidences: dict[str, float]):
    return [
        lambda _snap, tid=tid, c=c: TypologyResult(
            id=tid, points=0, confidence=c, reasons=[f"{tid}.stub"] if c > 0 else []
        )
        for tid, c in confidences.items()
    ]


def test_slow_multi_soft_floor_raises_allow_to_soft_challenge(monkeypatch):
    cal = load_calibration()
    friction, reasons = apply_soft_floors(
        FrictionAction.allow,
        snapshot={"accounts_on_device_7d": 5},
        confidences={"multi_account": 0.8},
        soft_floors=cal["soft_floors"],
    )
    assert friction == FrictionAction.soft_challenge
    assert "floor.soft.slow_multi" in reasons

    # evaluate: score stays band-allow but soft floor raises friction
    conf = {tid: 0.0 for tid in cal["weights"]}
    conf["multi_account"] = 0.70  # score≈24 at w=0.34; floor min_confidence 0.7
    monkeypatch.setattr("loyalty_abuse.score.ALL_SCORERS", _stub_scorers(conf))

    def fake_snapshot(_event):
        return {
            "accounts_on_device_7d": 5,
            "force_hard_floor": False,
            "liability_usd": 0.0,
        }

    monkeypatch.setattr(FeatureStore, "snapshot", lambda self, event: fake_snapshot(event))
    event = EventEnvelope(
        event_id="e1",
        tenant_id="t",
        ts="2026-08-05T00:00:00Z",
        type=EventType.redeem,
        account_id="a1",
        session_id="s1",
        device_id="d1",
        ip="1.1.1.1",
    )
    d = evaluate(event, FeatureStore())
    assert d.score == int(round(100.0 * float(cal["weights"]["multi_account"]) * 0.70))
    assert d.score <= int(cal["bands"]["allow_max"])
    assert d.friction == FrictionAction.soft_challenge
    assert d.features_snapshot.get("band_friction") == "allow"
    assert "floor.soft.slow_multi" in d.reasons


def test_soft_floor_never_lowers_hard_challenge():
    cal = load_calibration()
    friction, reasons = apply_soft_floors(
        FrictionAction.hard_challenge,
        snapshot={"accounts_on_device_7d": 5},
        confidences={"multi_account": 0.8},
        soft_floors=cal["soft_floors"],
    )
    assert friction == FrictionAction.hard_challenge
    assert "floor.soft.slow_multi" in reasons
