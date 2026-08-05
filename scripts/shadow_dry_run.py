#!/usr/bin/env python3
"""Chronological synthetic shadow dry-run: score then confirm labels later."""
from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from loyalty_abuse.features import FeatureStore  # noqa: E402
from loyalty_abuse.schema import EventEnvelope, FrictionAction  # noqa: E402
from loyalty_abuse.score import evaluate  # noqa: E402
from synth_eval import GENERATORS, _alloc, _geq  # noqa: E402

SOFT_PLUS = {
    FrictionAction.soft_challenge.value,
    FrictionAction.hard_challenge.value,
    FrictionAction.block.value,
}


def _day_base(start: datetime, day_index: int) -> datetime:
    return start + timedelta(days=day_index)


def run_dry_run(
    n: int = 200,
    seed: int = 42,
    days: int = 14,
    *,
    out: Path | None = None,
) -> dict[str, Any]:
    """Generate journeys day-by-day, shadow-score, then confirm labels for metrics."""
    if n < 1:
        raise ValueError("n must be >= 1")
    if days < 1:
        raise ValueError("days must be >= 1")

    rng = random.Random(seed)
    start = datetime(2026, 7, 1, 12, 0, 0, tzinfo=timezone.utc)
    labels = _alloc(n, rng)

    # Phase 1 — schedule subjects across days (chronological generation).
    scheduled: list[tuple[int, str, list[EventEnvelope]]] = []
    for idx, label in enumerate(labels):
        day_i = idx % days
        base = _day_base(start, day_i)
        # Jitter within the day so multi-event journeys stay ordered.
        base = base + timedelta(minutes=rng.randint(0, 600))
        subj = GENERATORS[label](idx, rng, base)
        scheduled.append((day_i, label, subj.events))

    # Flatten to (ts, day, label, event, is_scored) and sort chronologically.
    timeline: list[tuple[str, int, str, EventEnvelope, bool]] = []
    for day_i, label, events in scheduled:
        for j, ev in enumerate(events):
            timeline.append((ev.ts, day_i, label, ev, j == len(events) - 1))
    timeline.sort(key=lambda row: (row[0], row[3].event_id))

    stores: dict[str, FeatureStore] = defaultdict(FeatureStore)
    # Shadow recommendations collected without using labels yet.
    shadow_rows: list[dict[str, Any]] = []
    by_day_counts: dict[str, int] = {str(d): 0 for d in range(days)}

    for _ts, day_i, label, ev, is_scored in timeline:
        store = stores[ev.tenant_id]
        if is_scored:
            decision = evaluate(ev, store)  # evaluate() observes the scored event
            shadow_rows.append(
                {
                    "event_id": ev.event_id,
                    "day": day_i,
                    "recommended_friction": decision.friction.value,
                    "score": decision.score,
                    "expected_insult_usd": decision.expected_insult_usd,
                    # Label held aside until confirmation phase (generator truth).
                    "_label": label,
                }
            )
            by_day_counts[str(day_i)] += 1
        else:
            store.observe(ev)

    # Phase 2 — later confirm labels from generator truth; compute proxies.
    confirmed = []
    for row in shadow_rows:
        label = row.pop("_label")
        confirmed.append({**row, "label": label, "is_abuse": label != "clean"})

    soft_plus_n = sum(1 for r in confirmed if r["recommended_friction"] in SOFT_PLUS)
    soft_plus_abuse = sum(
        1 for r in confirmed if r["recommended_friction"] in SOFT_PLUS and r["is_abuse"]
    )
    abuse_n = sum(1 for r in confirmed if r["is_abuse"])
    clean_n = sum(1 for r in confirmed if not r["is_abuse"])
    clean_frictioned = sum(
        1
        for r in confirmed
        if not r["is_abuse"]
        and _geq(r["recommended_friction"], FrictionAction.throttle.value)
    )

    precision = soft_plus_abuse / soft_plus_n if soft_plus_n else 1.0
    recall = soft_plus_abuse / abuse_n if abuse_n else 1.0
    insult_proxy = clean_frictioned / clean_n if clean_n else 0.0

    friction_counts = Counter(r["recommended_friction"] for r in confirmed)
    by_label: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"n": 0, "friction": Counter()}
    )
    for r in confirmed:
        by_label[r["label"]]["n"] += 1
        by_label[r["label"]]["friction"][r["recommended_friction"]] += 1

    report: dict[str, Any] = {
        "n": n,
        "seed": seed,
        "days": days,
        "scored": len(confirmed),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "insult_proxy": round(insult_proxy, 4),
        "definitions": {
            "precision": "soft_challenge+ that are abuse / soft_challenge+",
            "recall": "abuse caught at soft_challenge+ / abuse",
            "insult_proxy": "clean with recommended >= throttle / clean",
        },
        "friction_counts": {a.value: friction_counts.get(a.value, 0) for a in FrictionAction},
        "by_label": {
            lab: {"n": row["n"], "friction": dict(row["friction"])}
            for lab, row in sorted(by_label.items())
        },
        "by_day": by_day_counts,
        "note": (
            "Synthetic chronological dry-run only. "
            "Production A+ requires ≥4 weeks shadow with real later-confirmed labels."
        ),
    }

    if out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2) + "\n")
    return report


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--n", type=int, default=200)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--days", type=int, default=14)
    p.add_argument("--out", type=Path, default=Path("artifacts/shadow_dry_run.json"))
    args = p.parse_args()
    report = run_dry_run(n=args.n, seed=args.seed, days=args.days, out=args.out)
    print(
        json.dumps(
            {
                "precision": report["precision"],
                "recall": report["recall"],
                "insult_proxy": report["insult_proxy"],
                "scored": report["scored"],
            },
            indent=2,
        )
    )
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
