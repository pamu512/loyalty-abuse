"""Cost-optimal friction knee selection (locked-validation unit tests)."""

from __future__ import annotations

import json
from pathlib import Path

from loyalty_abuse.eval.cost_thresholds import select_bands, total_labeled_cost

FIXTURE = Path(__file__).parent / "fixtures" / "threshold_val_labels.json"

# Match friction_v2_0 cost block (kept inline so test does not depend on cal file shape).
COST = {
    "C_fn_per_usd": 1.0,
    "C_fp": {
        "allow": 0.0,
        "throttle": 0.05,
        "soft_challenge": 0.25,
        "hard_challenge": 0.75,
        "block": 1.5,
    },
    "miss_fraction": {
        "allow": 1.0,
        "throttle": 0.85,
        "soft_challenge": 0.45,
        "hard_challenge": 0.15,
        "block": 0.0,
    },
}

BASELINE = {
    "allow_max": 24,
    "throttle_max": 44,
    "soft_max": 64,
    "hard_max": 84,
}


def test_huge_abuse_liability_prefers_stricter_knees():
    """When abuse labels carry huge liability, selected knees tighten vs baseline."""
    rows = json.loads(FIXTURE.read_text())
    selected = select_bands(rows, cost=COST, baseline=BASELINE)
    # Stricter = lower knee (more scores map to higher friction).
    assert selected["allow_max"] <= BASELINE["allow_max"]
    assert selected["throttle_max"] <= BASELINE["throttle_max"]
    assert selected["soft_max"] <= BASELINE["soft_max"]
    assert selected["hard_max"] <= BASELINE["hard_max"]
    assert (
        selected["allow_max"] < BASELINE["allow_max"]
        or selected["throttle_max"] < BASELINE["throttle_max"]
        or selected["soft_max"] < BASELINE["soft_max"]
        or selected["hard_max"] < BASELINE["hard_max"]
    )
    assert total_labeled_cost(rows, selected, COST) < total_labeled_cost(
        rows, BASELINE, COST
    )
