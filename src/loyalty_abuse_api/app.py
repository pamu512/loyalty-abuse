from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from loyalty_abuse import evaluate
from loyalty_abuse.features import FeatureStore
from loyalty_abuse.schema import Decision, EventEnvelope
from loyalty_abuse_api.analytics import build_summary
from loyalty_abuse_api.db import Database


class EventIngestRequest(EventEnvelope):
    evaluate: bool = False


class EvaluateRequest(BaseModel):
    event_id: str | None = None
    event: EventEnvelope | None = None


class ShadowEvaluateRequest(BaseModel):
    event_id: str | None = None
    event: EventEnvelope | None = None
    host_friction: str | None = None


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
