"""Unified friction + loyalty-economics decision envelope."""

from __future__ import annotations

from typing import Any

from loyalty_abuse.features import FeatureStore
from loyalty_abuse.multi_gate import evaluate_loyalty_economics
from loyalty_abuse.schema import EventEnvelope, POLICY_VERSION, SCHEMA_VERSION, UnifiedDecision
from loyalty_abuse.score import evaluate


def build_unified_decision(
    event: EventEnvelope,
    store: FeatureStore,
    *,
    feed_snapshot: dict[str, Any] | None = None,
    program_config: dict[str, Any] | None = None,
    cluster_entity_ids: list[str] | None = None,
    scope: dict[str, Any] | None = None,
    prior_gate_state: dict[str, Any] | None = None,
    evaluation_mode: str = "live",
) -> UnifiedDecision:
    if evaluation_mode not in {"shadow", "live"}:
        raise ValueError("evaluation_mode must be shadow or live")
    friction = evaluate(event, store)
    economics = evaluate_loyalty_economics(
        entity_id=event.account_id,
        feed_snapshot=feed_snapshot,
        program_config=program_config,
        cluster_entity_ids=cluster_entity_ids,
        scope=scope,
        prior_gate_state=prior_gate_state,
    )
    # Hard invariant: economics path must never claim order deny / friction block.
    policy = economics.get("policy") if isinstance(economics, dict) else None
    if not isinstance(policy, dict) or policy.get("order_decision_untouched") is not True:
        economics = dict(economics) if isinstance(economics, dict) else {}
        economics["policy"] = {
            **(policy if isinstance(policy, dict) else {}),
            "order_decision_untouched": True,
        }
    return UnifiedDecision(
        friction=friction,
        economics=economics,
        evaluation_mode=evaluation_mode,
        schema_version=SCHEMA_VERSION,
        policy_version=friction.policy_version or POLICY_VERSION,
    )
