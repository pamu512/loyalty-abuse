#!/usr/bin/env python3
"""Retrain Platt calibrator on a locked train window; gate writes on held-out ECE.

Fit uses only the chronological train split. Report ECE/Brier are computed on the
held-out report window — never used for fitting. Candidate params are written only
when held-out ECE <= threshold (default 0.05) or ``--force`` is set.
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
    ece,
    fit_platt,
    predict_platt,
)

ECE_THRESHOLD = 0.05


def load_label_rows(path: Path) -> list[dict[str, Any]]:
    raw = json.loads(path.read_text())
    if not isinstance(raw, list):
        raise ValueError(f"{path}: expected JSON array")
    for i, row in enumerate(raw):
        if not isinstance(row, dict):
            raise ValueError(f"{path}[{i}]: expected object")
        for key in ("score", "label_abuse", "ts"):
            if key not in row:
                raise ValueError(f"{path}[{i}]: missing required field {key!r}")
    return raw


def split_chronological(
    rows: list[dict[str, Any]],
    *,
    train_end: str | None = None,
    train_fraction: float = 0.7,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split label rows into train (inclusive) and report (exclusive) by ``ts``."""
    ordered = sorted(rows, key=lambda r: (str(r["ts"]), str(r.get("decision_id", ""))))
    if train_end is not None:
        train = [r for r in ordered if str(r["ts"]) <= train_end]
        report = [r for r in ordered if str(r["ts"]) > train_end]
    else:
        if not (0.0 < train_fraction < 1.0):
            raise ValueError("train_fraction must be in (0, 1)")
        n = len(ordered)
        if n < 2:
            raise ValueError("need at least two rows for chronological split")
        k = max(1, int(n * train_fraction))
        if k >= n:
            raise ValueError("train_fraction leaves no report rows")
        train = ordered[:k]
        report = ordered[k:]
    if not train:
        raise ValueError("empty train window")
    if not report:
        raise ValueError("empty report window")
    return train, report


def _scores_labels(rows: list[dict[str, Any]]) -> tuple[list[float], list[int]]:
    scores = [float(r["score"]) / 100.0 for r in rows]
    labels = [1 if r["label_abuse"] else 0 for r in rows]
    return scores, labels


def retrain_from_rows(
    rows: list[dict[str, Any]],
    *,
    train_end: str | None = None,
    train_fraction: float = 0.7,
    ece_threshold: float = ECE_THRESHOLD,
    force: bool = False,
) -> dict[str, Any]:
    """Fit Platt on train window; evaluate ECE/Brier on held-out report window."""
    train, report = split_chronological(
        rows, train_end=train_end, train_fraction=train_fraction
    )
    fit_s, fit_y = _scores_labels(train)
    rep_s, rep_y = _scores_labels(report)

    a, b = fit_platt(fit_s, fit_y)
    probs = [predict_platt(s, a, b) for s in rep_s]
    report_ece = ece(probs, rep_y, n_bins=10)
    report_brier = brier(probs, rep_y)

    meets = report_ece <= ece_threshold
    should_write = meets or force

    return {
        "method": "platt",
        "a": a,
        "b": b,
        "n_train": len(train),
        "n_report": len(report),
        "train_end": train_end,
        "train_fraction": None if train_end is not None else train_fraction,
        "report_ece": report_ece,
        "report_brier": report_brier,
        "ece_threshold": ece_threshold,
        "meets_ece_target": meets,
        "force": force,
        "should_write": should_write,
    }


def build_candidate_payload(result: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "version": "platt_candidate",
        "method": "platt",
        "a": result["a"],
        "b": result["b"],
        "n_train": result["n_train"],
        "n_report": result["n_report"],
        "report_ece": result["report_ece"],
        "report_brier": result["report_brier"],
        "ece_threshold": result["ece_threshold"],
        "meets_ece_target": result["meets_ece_target"],
        "force": result["force"],
    }
    if result["train_end"] is not None:
        payload["train_end"] = result["train_end"]
    else:
        payload["train_fraction"] = result["train_fraction"]
    if result["force"] and not result["meets_ece_target"]:
        payload["force_note"] = (
            "held-out ECE exceeded threshold; params written because --force was set"
        )
    return payload


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--labels", type=Path, required=True, help="Label-set JSON array")
    p.add_argument(
        "--out",
        type=Path,
        default=ROOT / "artifacts" / "calibration_candidate.json",
        help="Candidate calibrator params output path",
    )
    p.add_argument(
        "--artifact-out",
        type=Path,
        default=ROOT / "artifacts" / "retrain_calibration.json",
        help="Retrain metrics / gate artifact",
    )
    p.add_argument(
        "--train-end",
        help="Inclusive train window cutoff (ISO ts); rows after are held-out report",
    )
    p.add_argument(
        "--train-fraction",
        type=float,
        default=0.7,
        help="Chronological train fraction when --train-end is omitted (default 0.7)",
    )
    p.add_argument(
        "--ece-threshold",
        type=float,
        default=ECE_THRESHOLD,
        help="Max held-out ECE allowed without --force (default 0.05)",
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="Write candidate params even when held-out ECE exceeds threshold",
    )
    args = p.parse_args()

    rows = load_label_rows(args.labels)
    result = retrain_from_rows(
        rows,
        train_end=args.train_end,
        train_fraction=args.train_fraction,
        ece_threshold=args.ece_threshold,
        force=args.force,
    )

    artifact = {
        **result,
        "labels": str(args.labels),
        "out": str(args.out),
        "wrote_candidate": result["should_write"],
    }
    args.artifact_out.parent.mkdir(parents=True, exist_ok=True)
    args.artifact_out.write_text(json.dumps(artifact, indent=2) + "\n")

    if not result["should_write"]:
        print(
            json.dumps(
                {
                    "wrote_candidate": False,
                    "report_ece": result["report_ece"],
                    "ece_threshold": result["ece_threshold"],
                    "artifact_out": str(args.artifact_out),
                },
                indent=2,
            )
        )
        return 1

    payload = build_candidate_payload(result)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2) + "\n")

    print(
        json.dumps(
            {
                "wrote_candidate": True,
                "report_ece": result["report_ece"],
                "meets_ece_target": result["meets_ece_target"],
                "force": result["force"],
                "out": str(args.out),
                "artifact_out": str(args.artifact_out),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
