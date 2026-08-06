#!/usr/bin/env python3
"""Fit score→p calibrator from challenge-outcome / clawback label rows.

Fail-closed for production claims:
- Requires ≥1 row with provenance in {challenge_failed, challenge_abandoned, clawback}.
- Pure synth/red_team label sets exit 2 (cannot unlock live shadow readiness).
- Score-path only when ``band_friction`` present and friction == band (else keep row;
  floor hygiene needs band_friction on decisions).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from loyalty_abuse.calibrate import (  # noqa: E402
    brier,
    clear_platt_cache,
    ece,
    fit_platt,
    predict_platt,
    reliability_bins,
)

PRODUCTION_PROVENANCE = frozenset(
    {"challenge_failed", "challenge_abandoned", "clawback"}
)
# Spec / private claim lock / assert_live_shadow_readiness: production outcome ECE ≤ 0.05
ECE_TARGET = 0.05
PLATT_L2 = 1.0
PLATT_A_ABS_MAX = 12.0
MIN_ROWS = 30


def _load_rows(path: Path) -> list[dict[str, Any]]:
    raw = json.loads(path.read_text())
    if not isinstance(raw, list):
        raise ValueError(f"{path}: expected JSON array")
    return raw


def _score_path_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for r in rows:
        band = r.get("band_friction")
        fric = r.get("friction")
        if band is not None and fric is not None and str(band) != str(fric):
            continue
        out.append(r)
    return out


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--labels", type=Path, required=True)
    p.add_argument(
        "--out",
        type=Path,
        default=ROOT / "artifacts" / "platt_from_outcomes.json",
    )
    p.add_argument(
        "--metrics-out",
        type=Path,
        default=ROOT / "artifacts" / "calibration_from_outcomes.json",
    )
    args = p.parse_args()

    rows = _load_rows(args.labels)
    prod_n = sum(1 for r in rows if r.get("provenance") in PRODUCTION_PROVENANCE)
    if prod_n < 1:
        print(
            json.dumps(
                {
                    "error": "no_production_provenance",
                    "detail": (
                        "label set has no challenge_failed / challenge_abandoned / "
                        "clawback rows — refuse production calibration claim"
                    ),
                    "n": len(rows),
                },
                indent=2,
            )
        )
        return 2

    fit_rows = _score_path_rows(rows)
    if len(fit_rows) < MIN_ROWS:
        print(
            json.dumps(
                {
                    "error": "insufficient_rows",
                    "n": len(fit_rows),
                    "min": MIN_ROWS,
                },
                indent=2,
            )
        )
        return 1

    scores = [float(r["score"]) / 100.0 for r in fit_rows]
    labels = [1 if r["label_abuse"] else 0 for r in fit_rows]
    a, b = fit_platt(scores, labels, l2=PLATT_L2)
    probs = [predict_platt(s, a, b) for s in scores]
    selected_ece = ece(probs, labels, n_bins=10)
    selected_brier = brier(probs, labels)
    step = abs(a) >= PLATT_A_ABS_MAX
    meets = selected_ece <= ECE_TARGET and not step

    payload = {
        "version": "platt_from_outcomes",
        "method": "platt",
        "a": a,
        "b": b,
        "l2": PLATT_L2,
        "label_provenance": "challenge_outcome_or_clawback",
        "production_eligible": True,
        "n_production_provenance": prod_n,
        "score_path_only": True,
        "platt_rejected_step": step,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2) + "\n")
    clear_platt_cache()

    metrics = {
        "n": len(fit_rows),
        "n_production_provenance": prod_n,
        "platt": {"a": a, "b": b, "ece": selected_ece, "brier": selected_brier},
        "reliability_bins": reliability_bins(probs, labels, n_bins=10),
        "meets_ece_target": meets,
        "production_eligible": True,
        "out": str(args.out),
    }
    args.metrics_out.write_text(json.dumps(metrics, indent=2) + "\n")
    print(json.dumps(metrics, indent=2))
    return 0 if meets else 1


if __name__ == "__main__":
    raise SystemExit(main())
