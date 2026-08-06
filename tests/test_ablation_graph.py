"""Smoke: graph ablation runs on a tiny holdout and enforces household allow gate."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from ablation_graph import HOUSEHOLD_ALLOW_DROP_MAX_PP, run_ablation  # noqa: E402


def test_ablation_smoke_small_n():
    report = run_ablation(seed=42, n_per_slice=2)
    assert report["protocol"]["n_per_slice"] == 2
    assert report["counters_only"]["n"] == 12
    assert report["counters_plus_graph"]["n"] == 12
    assert "household_fp" in report["counters_only"]["slices"]
    assert "household_fp" in report["counters_plus_graph"]["slices"]
    assert report["deltas"]["household_allow_rate_drop_pp"] <= HOUSEHOLD_ALLOW_DROP_MAX_PP
    assert report["household_allow_gate_pass"] is True
    # catch slices present for both modes; graph-linked slice must show lift
    for name in (
        "device_rotation",
        "slow_multi_acct",
        "sequential_promo",
        "ato_known_device",
        "graph_payment_ring",
    ):
        assert name in report["deltas"]["catch_rate_graph_minus_counters"]
    assert report["deltas"]["catch_rate_graph_minus_counters"]["graph_payment_ring"] > 0
