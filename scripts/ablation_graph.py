#!/usr/bin/env python3
"""Counters-only vs counters+graph ablation on locked adversarial holdout (seed 42)."""
from __future__ import annotations

import argparse
import json
import random
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from loyalty_abuse.calibration import load_calibration  # noqa: E402
from loyalty_abuse.eval.adversarial import (  # noqa: E402
    GENERATORS,
    N_PER_SLICE,
    _geq,
)
from loyalty_abuse.schema import FrictionAction  # noqa: E402
from loyalty_abuse.eval.cost_thresholds import (  # noqa: E402
    _SLICE_ABUSE,
    liability_for_payload,
    total_labeled_cost,
)
from loyalty_abuse.features import FeatureStore  # noqa: E402
from loyalty_abuse.score import evaluate  # noqa: E402

GRAPH_KEYS = (
    "graph_cluster_size",
    "graph_multi_hop_accounts",
    "graph_age_diversity_hours",
    "graph_shared_attr_rarity",
)

# Graph must not hurt household allow_rate by more than this many percentage points.
HOUSEHOLD_ALLOW_DROP_MAX_PP = 5.0


def score_journey(events: list, *, use_graph: bool = True):
    """Score a journey; when use_graph=False, zero snapshot graph keys (typology channel off)."""
    store = FeatureStore()
    for e in events[:-1]:
        store.observe(e)
    if not use_graph:
        orig = store.snapshot

        def _snapshot_no_graph(event):
            snap = orig(event)
            for k in GRAPH_KEYS:
                snap[k] = 0.0
            return snap

        store.snapshot = _snapshot_no_graph  # type: ignore[method-assign]
    return evaluate(events[-1], store)


def _slice_metrics(frictions: list[str]) -> dict[str, Any]:
    n = len(frictions)
    allow_n = sum(1 for f in frictions if f == FrictionAction.allow.value)
    catch_n = sum(
        1 for f in frictions if _geq(FrictionAction(f), FrictionAction.soft_challenge)
    )
    return {
        "n": n,
        "friction": {a.value: frictions.count(a.value) for a in FrictionAction},
        "allow_rate": round(allow_n / n, 4) if n else 0.0,
        "catch_rate": round(catch_n / n, 4) if n else 0.0,
    }


def run_ablation(
    seed: int = 42,
    *,
    n_per_slice: int = N_PER_SLICE,
) -> dict[str, Any]:
    """Same holdout journeys; score counters-only vs counters+graph."""
    load_calibration.cache_clear()
    cal = load_calibration()
    cost = cal["cost"]
    bands = {
        "allow_max": int(cal["bands"]["allow_max"]),
        "throttle_max": int(cal["bands"]["throttle_max"]),
        "soft_max": int(cal["bands"]["soft_max"]),
        "hard_max": int(cal["bands"]["hard_max"]),
    }
    rng = random.Random(seed)
    base = datetime(2026, 8, 5, 12, 0, 0, tzinfo=timezone.utc)

    journeys: list[dict[str, Any]] = []
    for name, gen in GENERATORS.items():
        abuse = _SLICE_ABUSE[name]
        for j in range(n_per_slice):
            jr = random.Random(rng.randint(0, 2**31 - 1))
            events = gen(j, jr, base)
            journeys.append(
                {
                    "slice": name,
                    "label_abuse": abuse,
                    "liability_usd": liability_for_payload(
                        events[-1].payload, abuse=abuse
                    ),
                    "events": events,
                }
            )

    modes: dict[str, dict[str, Any]] = {}
    for mode_name, use_graph in (
        ("counters_only", False),
        ("counters_plus_graph", True),
    ):
        frictions_by_slice: dict[str, list[str]] = {n: [] for n in GENERATORS}
        rows: list[dict[str, Any]] = []
        for j in journeys:
            d = score_journey(j["events"], use_graph=use_graph)
            frictions_by_slice[j["slice"]].append(d.friction.value)
            rows.append(
                {
                    "score": int(d.score),
                    "liability_usd": j["liability_usd"],
                    "label_abuse": j["label_abuse"],
                    "slice": j["slice"],
                    "source": "adversarial",
                }
            )
        slices = {name: _slice_metrics(fs) for name, fs in frictions_by_slice.items()}
        modes[mode_name] = {
            "slices": slices,
            "labeled_cost": round(total_labeled_cost(rows, bands, cost), 4),
            "n": len(rows),
        }

    hh_c = float(modes["counters_only"]["slices"]["household_fp"]["allow_rate"])
    hh_g = float(modes["counters_plus_graph"]["slices"]["household_fp"]["allow_rate"])
    drop_pp = round((hh_c - hh_g) * 100.0, 4)
    gate_ok = drop_pp <= HOUSEHOLD_ALLOW_DROP_MAX_PP

    catch_delta: dict[str, float] = {}
    for name in GENERATORS:
        if name == "household_fp":
            continue
        c = float(modes["counters_only"]["slices"][name]["catch_rate"])
        g = float(modes["counters_plus_graph"]["slices"][name]["catch_rate"])
        catch_delta[name] = round(g - c, 4)

    return {
        "protocol": {
            "holdout": "adversarial labeled journeys",
            "seed": seed,
            "n_per_slice": n_per_slice,
            "counters_only": "snapshot graph_* zeroed (typology graph channel off)",
            "counters_plus_graph": "full FeatureStore graph features",
            "bands": bands,
            "household_allow_drop_max_pp": HOUSEHOLD_ALLOW_DROP_MAX_PP,
        },
        "policy_version": cal.get("policy_version"),
        "counters_only": modes["counters_only"],
        "counters_plus_graph": modes["counters_plus_graph"],
        "deltas": {
            "household_allow_rate_drop_pp": drop_pp,
            "catch_rate_graph_minus_counters": catch_delta,
            "labeled_cost_graph_minus_counters": round(
                modes["counters_plus_graph"]["labeled_cost"]
                - modes["counters_only"]["labeled_cost"],
                4,
            ),
        },
        "household_allow_gate_pass": gate_ok,
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--n-per-slice", type=int, default=N_PER_SLICE)
    p.add_argument(
        "--out",
        type=Path,
        default=Path("artifacts/graph_ablation_v2_0.json"),
    )
    args = p.parse_args()

    report = run_ablation(args.seed, n_per_slice=args.n_per_slice)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + "\n")

    summary = {
        "household_allow_gate_pass": report["household_allow_gate_pass"],
        "deltas": report["deltas"],
        "counters_only_cost": report["counters_only"]["labeled_cost"],
        "counters_plus_graph_cost": report["counters_plus_graph"]["labeled_cost"],
        "household_fp": {
            "counters_only_allow": report["counters_only"]["slices"]["household_fp"][
                "allow_rate"
            ],
            "graph_allow": report["counters_plus_graph"]["slices"]["household_fp"][
                "allow_rate"
            ],
        },
    }
    print(json.dumps(summary, indent=2))
    print(f"wrote {args.out}")
    return 0 if report["household_allow_gate_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
