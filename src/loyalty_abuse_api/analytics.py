from __future__ import annotations

from collections import Counter
from typing import Any

from loyalty_abuse.calibration import load_calibration
from loyalty_abuse.economics import expected_loss_usd, liability_usd
from loyalty_abuse.floors import FRICTION_ORDER
from loyalty_abuse.policy import FrictionPolicy
from loyalty_abuse.schema import EventEnvelope, FrictionAction, POLICY_VERSION

TYPOLOGY_IDS = (
    "multi_account",
    "referral_self_deal",
    "promo_stack",
    "bot_redeem",
    "code_leak",
    "ato_redeem",
)

_HARD_PLUS = frozenset({FrictionAction.hard_challenge.value, FrictionAction.block.value})


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


def _p50(values: list[int]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2 == 1:
        return float(ordered[mid])
    return (ordered[mid - 1] + ordered[mid]) / 2.0


def _insult_proxy(
    decisions: list[dict[str, Any]],
    shadow_logs: list[dict[str, Any]],
) -> float:
    # Prefer hard_challenge+ rate on allow-labeled shadow (host_friction == allow).
    allow_labeled = [row for row in shadow_logs if row.get("host_friction") == "allow"]
    if allow_labeled:
        hit = sum(1 for row in allow_labeled if row.get("recommended_friction") in _HARD_PLUS)
        return hit / len(allow_labeled)
    # Fallback: friction mix — hard_challenge+ share of audited decisions.
    if not decisions:
        return 0.0
    hit = sum(1 for d in decisions if str(d.get("friction") or "allow") in _HARD_PLUS)
    return hit / len(decisions)


def _expected_loss(
    decisions: list[dict[str, Any]],
    events_by_id: dict[str, EventEnvelope] | None,
) -> dict[str, Any]:
    policy_sum = sum(float(d.get("expected_loss_usd") or 0.0) for d in decisions)
    if not events_by_id:
        return {"policy_sum": policy_sum, "allow_all_sum": None}
    allow_all = 0.0
    economics = False
    for d in decisions:
        event = events_by_id.get(str(d.get("event_id") or ""))
        if event is None:
            continue
        liab = liability_usd(event)
        p_abuse = float(d.get("p_abuse") or 0.0)
        if liab > 0.0 or float(d.get("expected_loss_usd") or 0.0) > 0.0 or p_abuse > 0.0:
            economics = True
        allow_all += expected_loss_usd(liab, p_abuse, FrictionAction.allow)
    return {
        "policy_sum": policy_sum,
        "allow_all_sum": allow_all if economics else None,
    }


def _intel_metrics(intel_calls: list[dict[str, Any]]) -> dict[str, Any]:
    if not intel_calls:
        return {"success_rate": None, "p50_latency_ms": None}
    n = len(intel_calls)
    success_rate = sum(1 for row in intel_calls if row.get("success")) / n
    return {
        "success_rate": success_rate,
        "p50_latency_ms": _p50([int(row.get("latency_ms") or 0) for row in intel_calls]),
    }


def _friction_rank(value: str) -> int:
    try:
        return FRICTION_ORDER.index(FrictionAction(value))
    except ValueError:
        return 0


def _band_friction_for(decision: dict[str, Any]) -> str:
    snap = decision.get("features_snapshot") or {}
    band = snap.get("band_friction")
    if band:
        return str(band)
    cal = load_calibration()
    bands = cal["bands"]
    policy = FrictionPolicy(
        allow_max=int(bands["allow_max"]),
        throttle_max=int(bands["throttle_max"]),
        soft_max=int(bands["soft_max"]),
        hard_max=int(bands["hard_max"]),
        version=str(cal.get("policy_version") or POLICY_VERSION),
    )
    return policy.action_for(int(decision.get("score") or 0), force_hard_floor=False).value


def _floor_raised(decision: dict[str, Any]) -> bool:
    reasons = decision.get("reasons") or []
    if any(str(r).startswith("floor.soft.") for r in reasons):
        return True
    final = str(decision.get("friction") or "allow")
    band = _band_friction_for(decision)
    return _friction_rank(final) > _friction_rank(band)


def _floor_attribution(decisions: list[dict[str, Any]]) -> dict[str, Any]:
    count = len(decisions)
    raised = sum(1 for d in decisions if _floor_raised(d))
    return {
        "floor_raised_count": raised,
        "floor_raised_rate": (raised / count if count else 0.0),
    }


def _challenge_conversion(outcomes: list[dict[str, Any]]) -> float | None:
    counted = [
        row
        for row in outcomes
        if str(row.get("outcome") or "") in {"passed", "failed", "abandoned"}
    ]
    if not counted:
        return None
    passed = sum(1 for row in counted if row.get("outcome") == "passed")
    return passed / len(counted)


def build_ops_metrics(
    *,
    decisions: list[dict[str, Any]],
    shadow_logs: list[dict[str, Any]] | None = None,
    intel_calls: list[dict[str, Any]] | None = None,
    challenge_outcomes: list[dict[str, Any]] | None = None,
    events_by_id: dict[str, EventEnvelope] | None = None,
) -> dict[str, Any]:
    floor = _floor_attribution(decisions)
    return {
        "insult_proxy": _insult_proxy(decisions, shadow_logs or []),
        "expected_loss": _expected_loss(decisions, events_by_id),
        "intel_calls": _intel_metrics(intel_calls or []),
        "challenge_conversion": _challenge_conversion(challenge_outcomes or []),
        "floor_raised_count": floor["floor_raised_count"],
        "floor_raised_rate": floor["floor_raised_rate"],
    }


summarize_decisions = build_summary
