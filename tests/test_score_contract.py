import json
from pathlib import Path

import pytest

from loyalty_abuse import evaluate
from loyalty_abuse.calibration import load_calibration
from loyalty_abuse.features import FeatureStore
from loyalty_abuse.interactions import blend_raw, interaction_results
from loyalty_abuse.mathutil import clip
from loyalty_abuse.schema import EventEnvelope

GOLDEN = json.loads((Path(__file__).parent / "fixtures" / "golden_tiers.json").read_text())


@pytest.mark.parametrize("case", GOLDEN, ids=[c["name"] for c in GOLDEN])
def test_points_sum_matches_score(case):
    store = FeatureStore()
    events = [EventEnvelope(**e) for e in case["events"]]
    for e in events[:-1]:
        store.observe(e)
    d = evaluate(events[-1], store)
    pts = sum(t.points for t in d.typology_breakdown)
    assert abs(pts - d.score) <= 1
    assert d.policy_version == "friction_v2_3"


def test_points_sum_includes_interaction_rows():
    """sum(typology points + ix points) ≈ score ±1 for multi×promo."""
    cal = load_calibration()
    weights = cal["weights"]
    interactions = cal["interactions"]
    conf = {
        "ato_redeem": 0.0,
        "multi_account": 1.0,
        "bot_redeem": 0.0,
        "referral_self_deal": 0.0,
        "code_leak": 0.0,
        "promo_stack": 1.0,
    }
    score = int(round(100.0 * clip(blend_raw(weights, conf, interactions))))
    typ_pts = sum(int(round(100.0 * float(weights[tid]) * conf[tid])) for tid in weights)
    ix_pts = sum(r.points for r in interaction_results(conf, interactions) if r.points > 0)
    assert abs((typ_pts + ix_pts) - score) <= 1
    assert any(r.id.startswith("ix.") for r in interaction_results(conf, interactions) if r.points > 0)


def test_weighted_sum_no_max_weight_normalize():
    """Single typology at c=1 must score ~100*w, not 100 (no max_w rescale)."""
    store = FeatureStore()
    case = next(c for c in GOLDEN if c["name"] == "hard_ato_chain")
    events = [EventEnvelope(**e) for e in case["events"]]
    for e in events[:-1]:
        store.observe(e)
    d = evaluate(events[-1], store)
    ato = next(t for t in d.typology_breakdown if t.id == "ato_redeem")
    # No max_weight_normalize: lone ATO cannot hit score 100.
    w = float(load_calibration()["weights"]["ato_redeem"])
    assert ato.points == int(round(100.0 * w * ato.confidence))
    assert abs(d.score - ato.points) <= 1
    assert d.score < 50
