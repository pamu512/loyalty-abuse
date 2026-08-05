from __future__ import annotations

import uuid

from loyalty_abuse.calibrate import predict_calibrated
from loyalty_abuse.calibration import load_calibration
from loyalty_abuse.device_intel import (
    INTEL_HIGH_RISK_REASON,
    INTEL_UNAVAILABLE_REASON,
    intel_signals_hard_floor,
    intel_unavailable,
)
from loyalty_abuse.economics import expected_costs, liability_usd
from loyalty_abuse.features import FeatureStore
from loyalty_abuse.mathutil import clip
from loyalty_abuse.policy import FrictionPolicy
from loyalty_abuse.schema import Decision, EventEnvelope, POLICY_VERSION
from loyalty_abuse.typologies import ALL_SCORERS


def evaluate(
    event: EventEnvelope,
    store: FeatureStore,
    policy: FrictionPolicy | None = None,
) -> Decision:
    cal = load_calibration()
    bands = cal["bands"]
    policy = policy or FrictionPolicy(
        allow_max=int(bands["allow_max"]),
        throttle_max=int(bands["throttle_max"]),
        soft_max=int(bands["soft_max"]),
        hard_max=int(bands["hard_max"]),
        version=str(cal.get("policy_version") or POLICY_VERSION),
    )
    store.observe(event)
    snap = store.snapshot(event)
    results = [s(snap) for s in ALL_SCORERS]
    weights = cal["weights"]
    weighted = sum(float(weights.get(r.id) or 0.0) * float(r.confidence) for r in results)
    score = int(round(100.0 * clip(weighted)))
    active = [r for r in results if r.confidence > 0]
    reasons = [code for tr in active for code in tr.reasons]
    payload = event.payload if isinstance(event.payload, dict) else {}
    if intel_signals_hard_floor(snap) or intel_signals_hard_floor(payload):
        reasons.append(INTEL_HIGH_RISK_REASON)
    if intel_unavailable(snap) or intel_unavailable(payload):
        reasons.append(INTEL_UNAVAILABLE_REASON)
    friction = policy.action_for(score, force_hard_floor=bool(snap.get("force_hard_floor")))
    p_abuse = predict_calibrated(score / 100.0)
    loss_usd, insult_usd = expected_costs(
        liability_usd(event), p_abuse, friction, cost=cal.get("cost")
    )
    return Decision(
        decision_id="dec_" + uuid.uuid4().hex,
        event_id=event.event_id,
        score=score,
        friction=friction,
        reasons=reasons,
        typology_breakdown=active,
        features_snapshot=snap,
        policy_version=policy.version,
        expected_loss_usd=loss_usd,
        expected_insult_usd=insult_usd,
        p_abuse=p_abuse,
    )
