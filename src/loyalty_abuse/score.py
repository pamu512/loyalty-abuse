from __future__ import annotations

import uuid

from loyalty_abuse.features import FeatureStore
from loyalty_abuse.policy import FrictionPolicy
from loyalty_abuse.schema import Decision, EventEnvelope
from loyalty_abuse.typologies import ALL_SCORERS


def evaluate(
    event: EventEnvelope,
    store: FeatureStore,
    policy: FrictionPolicy | None = None,
) -> Decision:
    policy = policy or FrictionPolicy()
    store.observe(event)
    snap = store.snapshot(event)
    results = [s(snap) for s in ALL_SCORERS]
    results = [r for r in results if r.points > 0]
    score = min(100, sum(r.points for r in results))
    reasons = [r for tr in results for r in tr.reasons]
    friction = policy.action_for(score, force_hard_floor=bool(snap.get("force_hard_floor")))
    return Decision(
        decision_id="dec_" + uuid.uuid4().hex,
        event_id=event.event_id,
        score=score,
        friction=friction,
        reasons=reasons,
        typology_breakdown=results,
        features_snapshot=snap,
        policy_version=policy.version,
    )
