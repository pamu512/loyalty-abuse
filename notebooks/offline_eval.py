#!/usr/bin/env python3
"""Offline evaluation over persisted decisions."""

from __future__ import annotations

import argparse
import sys
from typing import Any

from loyalty_abuse.schema import FrictionAction
from loyalty_abuse_api.analytics import summarize_decisions
from loyalty_abuse_api.db import Database

__all__ = ["summarize_decisions", "friction_for_score", "threshold_sweep", "reason_coverage", "main"]

THRESHOLD_SETS: tuple[tuple[str, tuple[int, int, int, int]], ...] = (
    ("24/44/64/84", (24, 44, 64, 84)),
    ("20/40/60/80", (20, 40, 60, 80)),
)


def friction_for_score(
    score: int,
    *,
    allow_max: int,
    throttle_max: int,
    soft_max: int,
    hard_max: int,
) -> str:
    s = max(0, min(100, int(score)))
    if s <= allow_max:
        return FrictionAction.allow.value
    if s <= throttle_max:
        return FrictionAction.throttle.value
    if s <= soft_max:
        return FrictionAction.soft_challenge.value
    if s <= hard_max:
        return FrictionAction.hard_challenge.value
    return FrictionAction.block.value


def reason_coverage(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    with_reasons = sum(1 for row in rows if row.get("reasons"))
    unique = {str(reason) for row in rows for reason in (row.get("reasons") or [])}
    return {
        "with_reasons": with_reasons,
        "total": total,
        "pct": (with_reasons / total * 100.0) if total else 0.0,
        "unique_reasons": len(unique),
    }


def threshold_sweep(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for label, (allow_max, throttle_max, soft_max, hard_max) in THRESHOLD_SETS:
        counts = {action.value: 0 for action in FrictionAction}
        mismatches = 0
        for row in rows:
            score = int(row.get("score") or 0)
            recomputed = friction_for_score(
                score,
                allow_max=allow_max,
                throttle_max=throttle_max,
                soft_max=soft_max,
                hard_max=hard_max,
            )
            counts[recomputed] += 1
            stored = str(row.get("friction") or FrictionAction.allow.value)
            if recomputed != stored:
                mismatches += 1
        results.append(
            {
                "thresholds": label,
                "friction_counts": counts,
                "mismatch_vs_stored": mismatches,
            }
        )
    return results


def _load_rows(db_path: str) -> list[dict[str, Any]]:
    db = Database(db_path)
    return [decision.model_dump(mode="json") for decision in db.list_decisions()]


def _print_report(rows: list[dict[str, Any]]) -> None:
    summary = summarize_decisions(rows)
    print(f"decision_count={summary['decision_count']}")
    print("\nfriction_distribution (stored):")
    for action in FrictionAction:
        print(f"  {action.value}: {summary['friction_counts'].get(action.value, 0)}")

    coverage = reason_coverage(rows)
    print(
        f"\nreason_coverage: {coverage['with_reasons']}/{coverage['total']} "
        f"({coverage['pct']:.1f}%)"
    )
    print(f"unique_reasons: {coverage['unique_reasons']}")

    print(
        "\nthreshold_sweep:"
        f"\n{'thresholds':<14} {'allow':>6} {'throttle':>8} {'soft':>6} "
        f"{'hard':>6} {'block':>6} {'mismatch':>8}"
    )
    for entry in threshold_sweep(rows):
        counts = entry["friction_counts"]
        print(
            f"{entry['thresholds']:<14} "
            f"{counts.get('allow', 0):>6} "
            f"{counts.get('throttle', 0):>8} "
            f"{counts.get('soft_challenge', 0):>6} "
            f"{counts.get('hard_challenge', 0):>6} "
            f"{counts.get('block', 0):>6} "
            f"{entry['mismatch_vs_stored']:>8}"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Offline eval over decision DB")
    parser.add_argument("--db", required=True, help="Path to SQLite database")
    args = parser.parse_args(argv)
    try:
        rows = _load_rows(args.db)
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    _print_report(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
