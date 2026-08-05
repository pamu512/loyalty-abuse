#!/usr/bin/env python3
"""Fit Platt (seed 7) and report ECE/Brier on held-out seed 42. No sklearn."""

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
    ece,
    fit_binning,
    fit_platt,
    predict_binning,
    predict_platt,
    reliability_bins,
)
from loyalty_abuse.eval.cost_thresholds import build_adversarial_labeled_rows  # noqa: E402

LABEL_PROVENANCE = "synthetic red-team 2026-08-05"
ECE_TARGET = 0.05


def _xy(rows: list[dict[str, Any]]) -> tuple[list[float], list[int]]:
    scores = [float(r["score"]) / 100.0 for r in rows]
    labels = [1 if r["label_abuse"] else 0 for r in rows]
    return scores, labels


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--fit-seed", type=int, default=7)
    p.add_argument("--report-seed", type=int, default=42)
    p.add_argument(
        "--out",
        type=Path,
        default=ROOT / "src" / "loyalty_abuse" / "calibration" / "platt_v2_0.json",
    )
    p.add_argument(
        "--metrics-out",
        type=Path,
        default=ROOT / "artifacts" / "calibration_v2_0.json",
    )
    args = p.parse_args()

    # Bootstrap identity-ish file so evaluate() can load while we score fit rows.
    if not args.out.is_file():
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps(
                {
                    "version": "platt_v2_0",
                    "method": "platt",
                    "a": 1.0,
                    "b": 0.0,
                    "label_provenance": LABEL_PROVENANCE,
                },
                indent=2,
            )
            + "\n"
        )

    fit_rows = build_adversarial_labeled_rows(args.fit_seed)
    report_rows = build_adversarial_labeled_rows(args.report_seed)
    fit_s, fit_y = _xy(fit_rows)
    rep_s, rep_y = _xy(report_rows)

    a, b = fit_platt(fit_s, fit_y)
    platt_probs = [predict_platt(s, a, b) for s in rep_s]
    platt_ece = ece(platt_probs, rep_y, n_bins=10)
    platt_brier = brier(platt_probs, rep_y)
    platt_bins = reliability_bins(platt_probs, rep_y, n_bins=10)

    method = "platt"
    binning_payload: list[dict[str, float]] | None = None
    bin_ece = bin_brier = None
    bin_rel = None
    chosen_ece = platt_ece
    chosen_brier = platt_brier

    if platt_ece > ECE_TARGET:
        bins = fit_binning(fit_s, fit_y, n_bins=10)
        bin_probs = [predict_binning(s, bins) for s in rep_s]
        bin_ece = ece(bin_probs, rep_y, n_bins=10)
        bin_brier = brier(bin_probs, rep_y)
        bin_rel = reliability_bins(bin_probs, rep_y, n_bins=10)
        binning_payload = [
            {"lo": lo, "hi": hi, "p": p_hat} for lo, hi, p_hat in bins
        ]
        if bin_ece < platt_ece:
            method = "binning"
            chosen_ece = bin_ece
            chosen_brier = bin_brier

    payload: dict[str, Any] = {
        "version": "platt_v2_0",
        "method": method,
        "a": a,
        "b": b,
        "fit_seed": args.fit_seed,
        "report_seed": args.report_seed,
        "label_provenance": LABEL_PROVENANCE,
        "ece_target": ECE_TARGET,
    }
    if binning_payload is not None:
        payload["binning"] = binning_payload

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2) + "\n")

    from loyalty_abuse.calibrate import clear_platt_cache

    clear_platt_cache()

    metrics = {
        "label_provenance": LABEL_PROVENANCE,
        "fit_seed": args.fit_seed,
        "report_seed": args.report_seed,
        "n_fit": len(fit_s),
        "n_report": len(rep_s),
        "platt": {
            "a": a,
            "b": b,
            "ece": platt_ece,
            "brier": platt_brier,
            "reliability_bins": platt_bins,
        },
        "binning": (
            None
            if bin_ece is None
            else {"ece": bin_ece, "brier": bin_brier, "reliability_bins": bin_rel}
        ),
        "selected_method": method,
        "selected_ece": chosen_ece,
        "selected_brier": chosen_brier,
        "meets_ece_target": chosen_ece <= ECE_TARGET,
        "out": str(args.out),
    }

    args.metrics_out.parent.mkdir(parents=True, exist_ok=True)
    args.metrics_out.write_text(json.dumps(metrics, indent=2) + "\n")

    print(json.dumps(metrics, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
