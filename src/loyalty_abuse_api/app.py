from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from adapters.incognia import fetch_signals
from adapters.incognia.normalize import normalize_assessment
from loyalty_abuse import evaluate
from loyalty_abuse.device_intel import apply_to_payload
from loyalty_abuse.features import FeatureStore
from loyalty_abuse.schema import Decision, EventEnvelope, EventType
from loyalty_abuse_api.analytics import build_summary
from loyalty_abuse_api.db import Database

_FAIL_CLOSED_TYPES = frozenset({EventType.redeem, EventType.checkout})


def _env_flag(name: str, default: str = "false") -> bool:
    return os.environ.get(name, default).strip().lower() in {"1", "true", "yes", "on"}


def _request_token(payload: dict[str, Any]) -> str | None:
    tok = payload.get("request_token")
    if tok is None or tok == "":
        tok = payload.get("incognia_request_token")
    if tok is None or tok == "":
        return None
    return str(tok)


def _incognia_required(payload: dict[str, Any]) -> bool:
    if "incognia_required" in payload:
        return bool(payload["incognia_required"])
    return _env_flag("INCOGNIA_REQUIRED_DEFAULT", "false")


def _enrich_incognia(db: Database, event: EventEnvelope) -> EventEnvelope:
    """Fetch Incognia when token present; fail-closed injects device_intel_force_block."""
    payload = dict(event.payload) if isinstance(event.payload, dict) else {}
    token = _request_token(payload)
    if token is None:
        return event

    t0 = time.perf_counter()
    try:
        signals = fetch_signals(
            request_token=token,
            account_id=event.account_id,
            event_type=event.type.value,
            external_id=event.event_id,
        )
    except Exception:
        signals = normalize_assessment({}, source="unavailable")
    latency_ms = int(round((time.perf_counter() - t0) * 1000))
    source = getattr(signals, "source", None)
    db.log_intel_call(
        event_id=event.event_id,
        vendor="incognia",
        success=source != "unavailable",
        latency_ms=latency_ms,
        source=source if isinstance(source, str) else None,
    )
    payload = apply_to_payload(payload, signals)
    if (
        source == "unavailable"
        and _incognia_required(payload)
        and event.type in _FAIL_CLOSED_TYPES
    ):
        payload["device_intel_force_block"] = True
    return event.model_copy(update={"payload": payload})


class EventIngestRequest(EventEnvelope):
    evaluate: bool = False


class EvaluateRequest(BaseModel):
    event_id: str | None = None
    event: EventEnvelope | None = None


class ShadowEvaluateRequest(BaseModel):
    event_id: str | None = None
    event: EventEnvelope | None = None
    host_friction: str | None = None


class ChallengeOutcomeRequest(BaseModel):
    decision_id: str
    event_id: str | None = None
    outcome: Literal["passed", "failed", "abandoned"]
    ts: str


def _store_for_event(db: Database, event: EventEnvelope) -> FeatureStore:
    # Rebuild from DB; only prior events — evaluate() observes the scored event.
    store = FeatureStore()
    for prior in db.list_tenant_events(event.tenant_id, exclude_event_id=event.event_id):
        store.observe(prior)
    return store


def _resolve_event(db: Database, body: EvaluateRequest | ShadowEvaluateRequest) -> EventEnvelope:
    if body.event is not None:
        return body.event
    if body.event_id is not None:
        event = db.get_event(body.event_id)
        if event is None:
            raise HTTPException(status_code=404, detail="event not found")
        return event
    raise HTTPException(status_code=422, detail="event_id or event required")


def _run_evaluate(db: Database, event: EventEnvelope) -> Decision:
    event = _enrich_incognia(db, event)
    try:
        db.save_event(event)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="event persist failed") from exc

    store = _store_for_event(db, event)
    decision = evaluate(event, store)

    try:
        db.save_decision(decision)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="decision audit failed") from exc
    return decision


def _run_shadow_evaluate(
    db: Database,
    event: EventEnvelope,
    *,
    host_friction: str | None = None,
) -> Decision:
    event = _enrich_incognia(db, event)
    try:
        db.save_event(event)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="event persist failed") from exc

    store = _store_for_event(db, event)
    decision = evaluate(event, store)

    try:
        db.save_shadow_log(decision, host_friction=host_friction)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="shadow log failed") from exc
    return decision


def create_app(db_path: str | Path = "loyalty_abuse.db") -> FastAPI:
    app = FastAPI(title="loyalty-abuse")
    app.state.db = Database(db_path)

    @app.post("/v1/events")
    def post_events(body: EventIngestRequest) -> dict[str, Any]:
        event = EventEnvelope.model_validate(body.model_dump(exclude={"evaluate"}))
        if body.evaluate:
            return _run_evaluate(app.state.db, event).model_dump(mode="json")
        try:
            app.state.db.save_event(event)
        except Exception as exc:
            raise HTTPException(status_code=503, detail="event persist failed") from exc
        return {"event_id": event.event_id}

    @app.post("/v1/evaluate")
    def post_evaluate(body: EvaluateRequest) -> dict[str, Any]:
        event = _resolve_event(app.state.db, body)
        return _run_evaluate(app.state.db, event).model_dump(mode="json")

    @app.post("/v1/shadow/evaluate")
    def post_shadow_evaluate(body: ShadowEvaluateRequest) -> dict[str, Any]:
        event = _resolve_event(app.state.db, body)
        return _run_shadow_evaluate(
            app.state.db, event, host_friction=body.host_friction
        ).model_dump(mode="json")

    @app.get("/v1/decisions/{decision_id}")
    def get_decision(decision_id: str) -> dict[str, Any]:
        decision = app.state.db.get_decision(decision_id)
        if decision is None:
            raise HTTPException(status_code=404, detail="decision not found")
        return decision.model_dump(mode="json")

    @app.post("/v1/challenge_outcomes")
    def post_challenge_outcomes(body: ChallengeOutcomeRequest) -> dict[str, Any]:
        # Labels only — never rewrite decisions rows.
        try:
            return app.state.db.save_challenge_outcome(
                decision_id=body.decision_id,
                event_id=body.event_id,
                outcome=body.outcome,
                ts=body.ts,
            )
        except Exception as exc:
            raise HTTPException(status_code=503, detail="challenge outcome persist failed") from exc

    @app.get("/v1/analytics/summary")
    def get_analytics_summary() -> dict[str, Any]:
        rows = [d.model_dump(mode="json") for d in app.state.db.list_decisions()]
        return build_summary(rows)

    static_dir = Path(__file__).resolve().parent.parent.parent / "static"
    if static_dir.is_dir():
        app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")

    return app


_db_path = os.environ.get("LOYALTY_ABUSE_DB", "loyalty_abuse.db")
app = create_app(_db_path)
