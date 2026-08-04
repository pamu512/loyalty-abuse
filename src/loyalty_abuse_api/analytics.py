from __future__ import annotations

from collections import Counter
from typing import Any

from loyalty_abuse.schema import FrictionAction

TYPOLOGY_IDS = (
    "multi_account",
    "referral_self_deal",
    "promo_stack",
    "bot_redeem",
    "code_leak",
    "ato_redeem",
)


def _score_bucket(score: int) -> str:
    if score >= 100:
        return "100"
    lo = (score // 10) * 10
    return f"{lo}-{lo + 9}"


def build_summary(decisions: list[dict[str, Any]]) -> dict[str, Any]:
    friction_counts = {a.value: 0 for a in FrictionAction}
    score_histogram: dict[str, int] = {}
    reason_counter: Counter[str] = Counter()
    typology_hits: Counter[str] = Counter()

    for decision in decisions:
        friction = str(decision.get("friction") or "allow")
        if friction in friction_counts:
            friction_counts[friction] += 1

        bucket = _score_bucket(int(decision.get("score") or 0))
        score_histogram[bucket] = score_histogram.get(bucket, 0) + 1

        for reason in decision.get("reasons") or []:
            reason_counter[str(reason)] += 1

        for entry in decision.get("typology_breakdown") or []:
            if int(entry.get("points") or 0) > 0:
                typology_hits[str(entry.get("id") or "")] += 1

    count = len(decisions)
    typology_rates = {tid: (typology_hits.get(tid, 0) / count if count else 0.0) for tid in TYPOLOGY_IDS}
    for tid, hits in typology_hits.items():
        if tid not in typology_rates:
            typology_rates[tid] = hits / count if count else 0.0

    top_reasons = [{"reason": reason, "count": n} for reason, n in reason_counter.most_common(20)]

    return {
        "friction_counts": friction_counts,
        "score_histogram": score_histogram,
        "top_reasons": top_reasons,
        "typology_rates": typology_rates,
        "decision_count": count,
    }


summarize_decisions = build_summary
