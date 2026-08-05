#!/usr/bin/env python3
"""Synthetic 28-day shadow loop: events → decisions → outcomes → labels → metrics.

This sim exercises the shadow→label→retrain pipeline with generator truth.
It is **not** production A+ proof — live shadow requires ≥4 weeks with real labels.
"""
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
from build_label_set import build_label_rows  # noqa: E402
from retrain_calibration import retrain_from_rows  # noqa: E402
from shadow_dry_run import SOFT_PLUS, _day_base  # noqa: E402
from synth_eval import GENERATORS, _alloc, _geq  # noqa: E402

DAYS = 28
WEEKS = 4
BANNER = (
    "NOT PRODUCTION A+ — synthetic 28-day simulation only. "
    "Production A+/A++ requires live shadow ≥4 weeks with real later-confirmed outcome labels."
)


def _metrics(rows: list[dict[str, Any]]) -> dict[str, float]:
    soft_plus_n = sum(1 for r in rows if r["recommended_friction"] in SOFT_PLUS)
    soft_plus_abuse = sum(
        1 for r in rows if r["recommended_friction"] in SOFT_PLUS and r["is_abuse"]
    )
    abuse_n = sum(1 for r in rows if r["is_abuse"])
    clean_n = sum(1 for r in rows if not r["is_abuse"])
    clean_frictioned = sum(
        1
        for r in rows
        if not r["is_abuse"]
        and _geq(r["recommended_friction"], FrictionAction.throttle.value)
    )
    precision = soft_plus_abuse / soft_plus_n if soft_plus_n else 1.0
    recall = soft_plus_abuse / abuse_n if abuse_n else 1.0
    insult_proxy = clean_frictioned / clean_n if clean_n else 0.0
    return {
        "scored": len(rows),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "insult_proxy": round(insult_proxy, 4),
    }


def _outcome_ts(event_ts: str, rng: random.Random) -> str:
    base = datetime.fromisoformat(event_ts.replace("Z", "+00:00"))
    later = base + timedelta(hours=rng.randint(1, 72))
    return later.strftime("%Y-%m-%dT%H:%M:%SZ")


def run_four_week_sim(
    n: int = 280,
    seed: int = 42,
    days: int = DAYS,
    *,
    out: Path | None = None,
) -> dict[str, Any]:
    """Chronological 28-day shadow loop with synth decisions, outcomes, and weekly rollups."""
    if n < 1:
        raise ValueError("n must be >= 1")
    if days < 1:
        raise ValueError("days must be >= 1")

    rng = random.Random(seed)
    start = datetime(2026, 7, 1, 12, 0, 0, tzinfo=timezone.utc)
    labels = _alloc(n, rng)

    scheduled: list[tuple[int, str, list[EventEnvelope]]] = []
    for idx, label in enumerate(labels):
        day_i = idx % days
        base = _day_base(start, day_i) + timedelta(minutes=rng.randint(0, 600))
        subj = GENERATORS[label](idx, rng, base)
        scheduled.append((day_i, label, subj.events))

    timeline: list[tuple[str, int, str, EventEnvelope, bool]] = []
    for day_i, label, events in scheduled:
        for j, ev in enumerate(events):
            timeline.append((ev.ts, day_i, label, ev, j == len(events) - 1))
    timeline.sort(key=lambda row: (row[0], row[3].event_id))

    stores: dict[str, FeatureStore] = defaultdict(FeatureStore)
    confirmed: list[dict[str, Any]] = []
    decisions: list[dict[str, Any]] = []
    outcomes: list[dict[str, Any]] = []
    by_day_counts: dict[str, int] = {str(d): 0 for d in range(days)}

    for _ts, day_i, label, ev, is_scored in timeline:
        store = stores[ev.tenant_id]
        if is_scored:
            decision = evaluate(ev, store)
            friction = decision.friction.value
            is_abuse = label != "clean"
            decision_id = f"sim_{ev.event_id}"
            row = {
                "event_id": ev.event_id,
                "decision_id": decision_id,
                "day": day_i,
                "week": day_i // 7,
                "recommended_friction": friction,
                "host_friction": "allow",
                "score": decision.score,
                "p_abuse": decision.p_abuse,
                "label": label,
                "is_abuse": is_abuse,
                "ts": ev.ts,
            }
            confirmed.append(row)
            by_day_counts[str(day_i)] += 1

            decisions.append(
                {
                    "decision_id": decision_id,
                    "event_id": ev.event_id,
                    "score": decision.score,
                    "p_abuse": decision.p_abuse,
                    "friction": friction,
                    "provenance": "synth",
                    "label_abuse": is_abuse,
                    "ts": ev.ts,
                }
            )

            if friction in SOFT_PLUS:
                outcomes.append(
                    {
                        "decision_id": decision_id,
                        "outcome": "failed" if is_abuse else "passed",
                        "ts": _outcome_ts(ev.ts, rng),
                    }
                )
        else:
            store.observe(ev)

    overall = _metrics(confirmed)
    by_week: dict[str, dict[str, Any]] = {}
    for w in range(WEEKS):
        week_rows = [r for r in confirmed if r["week"] == w]
        by_week[str(w)] = _metrics(week_rows)

    label_rows = build_label_rows(decisions, outcomes)
    retrain_candidate: dict[str, Any] = {"evaluated": False}
    if len(label_rows) >= 2:
        try:
            result = retrain_from_rows(label_rows, train_fraction=0.7)
            retrain_candidate = {
                "evaluated": True,
                "n_labels": len(label_rows),
                "report_ece": round(result["report_ece"], 6),
                "report_brier": round(result["report_brier"], 6),
                "meets_ece_target": result["meets_ece_target"],
                "would_promote": result["should_write"],
                "note": "Sim candidate only — do not overwrite published calibration from sim.",
            }
        except ValueError as exc:
            retrain_candidate = {"evaluated": False, "error": str(exc)}

    friction_counts = Counter(r["recommended_friction"] for r in confirmed)
    report: dict[str, Any] = {
        "banner": BANNER,
        "n": n,
        "seed": seed,
        "days": days,
        "weeks": WEEKS,
        **overall,
        "definitions": {
            "precision": "soft_challenge+ that are abuse / soft_challenge+",
            "recall": "abuse caught at soft_challenge+ / abuse",
            "insult_proxy": "clean with recommended >= throttle / clean",
        },
        "friction_counts": {a.value: friction_counts.get(a.value, 0) for a in FrictionAction},
        "by_day": by_day_counts,
        "by_week": by_week,
        "pipeline": {
            "decisions": len(decisions),
            "outcomes": len(outcomes),
            "label_rows": len(label_rows),
        },
        "retrain_candidate": retrain_candidate,
        "note": BANNER,
    }

    if out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2) + "\n")
    return report


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--n", type=int, default=280, help="Synthetic subjects (default 280)")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--days", type=int, default=DAYS)
    p.add_argument(
        "--out",
        type=Path,
        default=Path("artifacts/shadow_four_week_sim.json"),
    )
    args = p.parse_args()
    report = run_four_week_sim(n=args.n, seed=args.seed, days=args.days, out=args.out)
    print(BANNER)
    print(
        json.dumps(
            {
                "precision": report["precision"],
                "recall": report["recall"],
                "insult_proxy": report["insult_proxy"],
                "scored": report["scored"],
                "label_rows": report["pipeline"]["label_rows"],
            },
            indent=2,
        )
    )
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
