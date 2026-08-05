import json
from pathlib import Path

import pytest

from loyalty_abuse import evaluate
from loyalty_abuse.features import FeatureStore
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
    assert d.policy_version == "friction_v1_2"


def test_weighted_sum_no_max_weight_normalize():
    """Single typology at c=1 must score ~100*w, not 100 (no max_w rescale)."""
    store = FeatureStore()
    case = next(c for c in GOLDEN if c["name"] == "hard_ato_chain")
    events = [EventEnvelope(**e) for e in case["events"]]
    for e in events[:-1]:
        store.observe(e)
    d = evaluate(events[-1], store)
    ato = next(t for t in d.typology_breakdown if t.id == "ato_redeem")
    # w=0.22, c=0.85 → points ≈ 19; without max_w, score stays near that
    assert ato.points == 19
    assert abs(d.score - 19) <= 1
