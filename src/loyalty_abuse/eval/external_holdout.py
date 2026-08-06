"""Frozen external journey pack — not produced by adversarial generators at eval time.

Journeys are hand-frozen JSON event sequences. Passing this pack proves catch/allow
bounds without trusting the cooperative generator loop that built training data.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from loyalty_abuse.features import FeatureStore
from loyalty_abuse.schema import EventEnvelope, FrictionAction
from loyalty_abuse.score import evaluate

FRICTION_ORDER = [
    FrictionAction.allow,
    FrictionAction.throttle,
    FrictionAction.soft_challenge,
    FrictionAction.hard_challenge,
    FrictionAction.block,
]

DEFAULT_PACK = (
    Path(__file__).resolve().parents[3]
    / "tests"
    / "fixtures"
    / "external_journeys.json"
)


def _geq(friction: FrictionAction, minimum: FrictionAction) -> bool:
    return FRICTION_ORDER.index(friction) >= FRICTION_ORDER.index(minimum)


def _score_events(raw_events: list[dict[str, Any]]):
    events = [EventEnvelope.model_validate(e) for e in raw_events]
    if not events:
        raise ValueError("empty journey")
    store = FeatureStore()
    for e in events[:-1]:
        store.observe(e)
    return evaluate(events[-1], store)


def load_pack(path: Path | None = None) -> list[dict[str, Any]]:
    p = path or DEFAULT_PACK
    data = json.loads(p.read_text())
    if not isinstance(data, list) or not data:
        raise ValueError(f"{p}: expected non-empty JSON array")
    return data


def run_external_holdout(path: Path | None = None) -> dict[str, Any]:
    pack = load_pack(path)
    results: list[dict[str, Any]] = []
    gates: dict[str, dict[str, Any]] = {}
    failures = 0
    for journey in pack:
        jid = str(journey["id"])
        d = _score_events(journey["events"])
        expect = journey.get("expect") or {}
        min_fric = expect.get("min_friction")
        max_fric = expect.get("max_friction")
        ok = True
        if min_fric is not None and not _geq(d.friction, FrictionAction(min_fric)):
            ok = False
        if max_fric is not None and FRICTION_ORDER.index(d.friction) > FRICTION_ORDER.index(
            FrictionAction(max_fric)
        ):
            ok = False
        max_p = expect.get("max_p_abuse")
        if max_p is not None and float(d.p_abuse) > float(max_p):
            ok = False
        min_p = expect.get("min_p_abuse")
        if min_p is not None and float(d.p_abuse) < float(min_p):
            ok = False
        if not ok:
            failures += 1
        results.append(
            {
                "id": jid,
                "label": journey.get("label"),
                "score": int(d.score),
                "friction": d.friction.value,
                "p_abuse": round(float(d.p_abuse), 4),
                "pass": ok,
            }
        )
        gates[jid] = {"pass": ok, "actual_friction": d.friction.value}

    return {
        "n": len(pack),
        "failures": failures,
        "gates_pass": failures == 0,
        "journeys": results,
        "gates": gates,
        "source": "frozen_external_pack",
    }
