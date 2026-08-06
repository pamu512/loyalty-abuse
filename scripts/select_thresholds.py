#!/usr/bin/env python3
"""Select friction knees on locked val seed; report cost on held-out seed (no retune)."""
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
sys.path.insert(0, str(ROOT / "scripts"))

from loyalty_abuse.calibration import load_calibration  # noqa: E402
from loyalty_abuse.eval.cost_thresholds import (  # noqa: E402
    DEFAULT_BASELINE,
    build_adversarial_labeled_rows,
    liability_for_payload,
    select_bands,
    total_labeled_cost,
)
from loyalty_abuse.features import FeatureStore  # noqa: E402
from loyalty_abuse.score import evaluate  # noqa: E402

import synth_eval  # noqa: E402


def _chronological_synth_rows(seed: int, n: int = 200) -> list[dict[str, Any]]:
    """Report-only chronological synth window (never used to select knees)."""
    rng = random.Random(seed)
    base = datetime(2026, 8, 1, 0, 0, 0, tzinfo=timezone.utc)
    labels = synth_eval._alloc(n, rng)
    rows: list[dict[str, Any]] = []
    for idx, label in enumerate(labels):
        day_base = base.replace(day=1 + (idx % 28))
        subj = synth_eval.GENERATORS[label](idx, rng, day_base)
        store = FeatureStore()
        for e in subj.events[:-1]:
            store.observe(e)
        d = evaluate(subj.events[-1], store)
        abuse = label != "clean"
        rows.append(
            {
                "score": int(d.score),
                "liability_usd": liability_for_payload(
                    subj.events[-1].payload, abuse=abuse
                ),
                "label_abuse": abuse,
                "slice": label,
                "source": "chronological_synth",
            }
        )
    return rows


def _write_cal_bands(bands: dict[str, int]) -> Path:
    path = ROOT / "src" / "loyalty_abuse" / "calibration" / "friction_v2_3.json"
    data = json.loads(path.read_text())
    data["bands"] = {
        "allow_max": int(bands["allow_max"]),
        "throttle_max": int(bands["throttle_max"]),
        "soft_max": int(bands["soft_max"]),
        "hard_max": int(bands["hard_max"]),
    }
    path.write_text(json.dumps(data, indent=2) + "\n")
    load_calibration.cache_clear()
    return path


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--val-seed", type=int, default=7)
    p.add_argument("--report-seed", type=int, default=42)
    p.add_argument(
        "--out",
        type=Path,
        default=Path("artifacts/threshold_selection_v2_0.json"),
    )
    p.add_argument(
        "--update-cal",
        action="store_true",
        help="Write selected bands into friction_v2_3.json (val seed only).",
    )
    p.add_argument("--synth-n", type=int, default=200)
    p.add_argument(
        "--baseline-bands",
        type=str,
        default=None,
        help=(
            "JSON object for frozen pre-selection baseline "
            f"(default: {json.dumps(DEFAULT_BASELINE)})."
        ),
    )
    args = p.parse_args()

    if args.val_seed == args.report_seed:
        print("error: val-seed and report-seed must differ (locked validation)", file=sys.stderr)
        return 2

    load_calibration.cache_clear()
    cal = load_calibration()
    cost = cal["cost"]
    # Frozen pre-selection baseline — not live cal bands (re-runs after --update-cal).
    if args.baseline_bands:
        baseline = json.loads(args.baseline_bands)
        for k in ("allow_max", "throttle_max", "soft_max", "hard_max"):
            if k not in baseline:
                print(f"error: baseline-bands missing {k!r}", file=sys.stderr)
                return 2
    else:
        baseline = dict(DEFAULT_BASELINE)

    # --- selection: val seed only ---
    val_rows = build_adversarial_labeled_rows(args.val_seed)
    selected = select_bands(val_rows, cost=cost, baseline=baseline)
    val_cost_base = total_labeled_cost(val_rows, baseline, cost)
    val_cost_sel = total_labeled_cost(val_rows, selected, cost)

    # --- report: seed 42 adversarial + chronological synth (no re-select) ---
    report_adv = build_adversarial_labeled_rows(args.report_seed)
    report_synth = _chronological_synth_rows(args.report_seed, n=args.synth_n)
    report_rows = report_adv + report_synth
    report_cost_base = total_labeled_cost(report_rows, baseline, cost)
    report_cost_sel = total_labeled_cost(report_rows, selected, cost)

    improved = val_cost_sel < val_cost_base - 1e-9
    cal_path = None
    if args.update_cal and improved:
        cal_path = str(_write_cal_bands(selected))
    elif args.update_cal and not improved:
        print("bands unchanged (no val-cost improvement vs baseline)")

    artifact = {
        "protocol": {
            "val_seed": args.val_seed,
            "report_seed": args.report_seed,
            "selection_source": "adversarial+household labels",
            "report_source": "adversarial seed + chronological synth",
            "hard_floor": "ignored during selection",
        },
        "baseline_bands": baseline,
        "selected_bands": selected,
        "improved_on_val": improved,
        "val": {
            "n": len(val_rows),
            "cost_baseline": round(val_cost_base, 4),
            "cost_selected": round(val_cost_sel, 4),
        },
        "report": {
            "n_adversarial": len(report_adv),
            "n_chronological_synth": len(report_synth),
            "n": len(report_rows),
            "cost_baseline": round(report_cost_base, 4),
            "cost_selected": round(report_cost_sel, 4),
        },
        "cost_model": cost,
        "calibration_updated": cal_path,
        "policy_version": cal.get("policy_version"),
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(artifact, indent=2) + "\n")
    print(json.dumps({k: artifact[k] for k in ("selected_bands", "val", "report", "improved_on_val")}, indent=2))
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
