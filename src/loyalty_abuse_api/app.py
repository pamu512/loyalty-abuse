from __future__ import annotations

import json
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Any, Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from adapters.consortium import lookup_badness
from adapters.incognia import env_creds_ready, fetch_signals
from adapters.incognia.normalize import normalize_assessment
from loyalty_abuse import evaluate
from loyalty_abuse.device_intel import apply_to_payload
from loyalty_abuse.envelope import build_unified_decision
from loyalty_abuse.features import FeatureStore
from loyalty_abuse.schema import Decision, EventEnvelope, EventType, UnifiedDecision
from loyalty_abuse_api.analytics import build_ops_metrics, build_summary
from loyalty_abuse_api.auth import (
    ApiPrincipal,
    bootstrap_admin_key,
    constant_time_equal,
    parse_bearer,
)
from loyalty_abuse_api.db import Database
from loyalty_abuse_api.metrics import METRICS
from loyalty_abuse_api.ratelimit import RateLimitExceeded, RateLimiter

_FAIL_CLOSED_TYPES = frozenset({EventType.redeem, EventType.checkout})

logging.basicConfig(level=logging.INFO)
_log = logging.getLogger("loyalty_abuse_api")


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


def _incognia_use_fixture(payload: dict[str, Any]) -> bool:
    return bool(payload.get("incognia_fixture") or payload.get("incognia_use_fixture"))


def _log_and_apply_intel(
    db: Database,
    event: EventEnvelope,
    payload: dict[str, Any],
    signals: Any,
    *,
    latency_ms: int,
    force_block: bool,
) -> EventEnvelope:
    source = getattr(signals, "source", None)
    db.log_intel_call(
        event_id=event.event_id,
        vendor="incognia",
        success=source != "unavailable",
        latency_ms=latency_ms,
        source=source if isinstance(source, str) else None,
    )
    payload = apply_to_payload(payload, signals)
    if force_block:
        payload["device_intel_force_block"] = True
    return event.model_copy(update={"payload": payload})


def _enrich_incognia(db: Database, event: EventEnvelope) -> EventEnvelope:
    """Fetch Incognia when token present; fail-closed injects device_intel_force_block.

    Missing env creds with a token → unavailable (no silent low_risk fixture) unless
    payload sets ``incognia_fixture`` / ``incognia_use_fixture``. Required redeem/checkout
    with no token also fail-closed.
    """
    payload = dict(event.payload) if isinstance(event.payload, dict) else {}
    token = _request_token(payload)
    required = _incognia_required(payload)
    fail_closed_type = event.type in _FAIL_CLOSED_TYPES
    use_fixture = _incognia_use_fixture(payload)

    if token is None:
        if required and fail_closed_type:
            t0 = time.perf_counter()
            signals = normalize_assessment({}, source="unavailable")
            latency_ms = int(round((time.perf_counter() - t0) * 1000))
            return _log_and_apply_intel(
                db,
                event,
                payload,
                signals,
                latency_ms=latency_ms,
                force_block=True,
            )
        return event

    t0 = time.perf_counter()
    try:
        if not use_fixture and not env_creds_ready():
            signals = normalize_assessment({}, source="unavailable")
        else:
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
    force_block = source == "unavailable" and required and fail_closed_type
    return _log_and_apply_intel(
        db,
        event,
        payload,
        signals,
        latency_ms=latency_ms,
        force_block=force_block,
    )


def _entity_hashes(event: EventEnvelope) -> list[str]:
    return [
        str(v)
        for v in (event.account_id, event.device_id, event.payment_instrument_hash)
        if v
    ]


def _enrich_consortium(event: EventEnvelope) -> EventEnvelope:
    """Attach typed consortium stub. Redeem/checkout cannot treat missing feed as clean."""
    if event.type not in _FAIL_CLOSED_TYPES:
        return event
    payload = dict(event.payload) if isinstance(event.payload, dict) else {}
    payload["consortium"] = lookup_badness(_entity_hashes(event))
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


class DecideRequest(BaseModel):
    event_id: str | None = None
    event: EventEnvelope | None = None
    feed_snapshot: dict[str, Any] | None = None
    program_config: dict[str, Any] | None = None
    cluster_entity_ids: list[str] | None = None
    scope: dict[str, Any] | None = None
    prior_gate_state: dict[str, Any] | None = None
    evaluation_mode: str | None = None


class CreateKeyRequest(BaseModel):
    tenant_id: str
    name: str = "default"
    scopes: list[str] = Field(default_factory=lambda: ["evaluate", "read", "export"])
    rpm: int = 120


class SetModeRequest(BaseModel):
    evaluation_mode: Literal["shadow", "live"]


def _store_for_event(db: Database, event: EventEnvelope) -> FeatureStore:
    store = FeatureStore()
    for prior in db.list_tenant_events(event.tenant_id, exclude_event_id=event.event_id):
        store.observe(prior)
    return store


def _resolve_event(db: Database, body: EvaluateRequest | ShadowEvaluateRequest | DecideRequest) -> EventEnvelope:
    if body.event is not None:
        return body.event
    if body.event_id is not None:
        event = db.get_event(body.event_id)
        if event is None:
            raise HTTPException(status_code=404, detail="event not found")
        return event
    raise HTTPException(status_code=422, detail="event_id or event required")


def create_app(db_path: str | Path = "loyalty_abuse.db") -> FastAPI:
    app = FastAPI(title="loyalty-abuse")
    app.state.db = Database(db_path)
    app.state.limiter = RateLimiter()

    @app.middleware("http")
    async def request_metrics(request: Request, call_next):
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
        request.state.request_id = request_id
        t0 = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        METRICS.observe_request(request.method, response.status_code)
        response.headers["X-Request-Id"] = request_id
        _log.info(
            json.dumps(
                {
                    "msg": "request",
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "latency_ms": round(elapsed_ms, 2),
                }
            )
        )
        return response

    def require_principal(
        authorization: str | None = Header(default=None),
    ) -> ApiPrincipal:
        if _env_flag("LOYALTY_ABUSE_AUTH_DISABLED", "false"):
            return ApiPrincipal(
                key_id="auth_disabled",
                tenant_id="*",
                scopes=frozenset({"admin", "evaluate", "read", "export"}),
                rpm=100_000,
                is_admin=True,
            )
        admin = bootstrap_admin_key()
        raw = parse_bearer(authorization)
        if raw is None:
            raise HTTPException(status_code=401, detail="missing bearer token")
        if admin and constant_time_equal(raw, admin):
            return ApiPrincipal(
                key_id="bootstrap_admin",
                tenant_id="*",
                scopes=frozenset({"admin", "evaluate", "read", "export"}),
                rpm=10_000,
                is_admin=True,
            )
        row = app.state.db.lookup_api_key(raw)
        if row is None:
            raise HTTPException(status_code=401, detail="invalid api key")
        try:
            app.state.limiter.check(row["key_id"], int(row["rpm"]))
        except RateLimitExceeded as exc:
            raise HTTPException(
                status_code=429,
                detail="rate limit exceeded",
                headers={"Retry-After": str(int(exc.retry_after))},
            ) from exc
        return ApiPrincipal(
            key_id=row["key_id"],
            tenant_id=row["tenant_id"],
            scopes=row["scopes"],
            rpm=int(row["rpm"]),
        )

    def assert_tenant(principal: ApiPrincipal, tenant_id: str) -> None:
        if principal.is_admin:
            return
        if principal.tenant_id != tenant_id:
            raise HTTPException(status_code=403, detail="tenant mismatch")

    def _run_evaluate(db: Database, event: EventEnvelope) -> Decision:
        event = _enrich_incognia(db, event)
        try:
            db.save_event(event)
        except Exception as exc:
            raise HTTPException(status_code=503, detail="event persist failed") from exc

        store = _store_for_event(db, event)
        t0 = time.perf_counter()
        decision = evaluate(event, store)
        METRICS.observe_evaluate_latency((time.perf_counter() - t0) * 1000.0)
        METRICS.observe_friction(decision.friction.value)

        try:
            db.save_decision(decision, tenant_id=event.tenant_id)
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
        METRICS.observe_friction(decision.friction.value)

        try:
            db.save_shadow_log(
                decision, host_friction=host_friction, tenant_id=event.tenant_id
            )
        except Exception as exc:
            raise HTTPException(status_code=503, detail="shadow log failed") from exc
        return decision

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz")
    def readyz() -> dict[str, str]:
        if not app.state.db.ping_writable():
            raise HTTPException(status_code=503, detail="db not ready")
        return {"status": "ready"}

    @app.get("/metrics")
    def metrics() -> Response:
        return PlainTextResponse(METRICS.render(), media_type="text/plain; version=0.0.4")

    @app.post("/v1/admin/keys")
    def create_key(
        body: CreateKeyRequest,
        principal: ApiPrincipal = Depends(require_principal),
    ) -> dict[str, Any]:
        if not principal.has_scope("admin"):
            raise HTTPException(status_code=403, detail="admin scope required")
        raw, key_id = app.state.db.create_api_key(
            tenant_id=body.tenant_id,
            name=body.name,
            scopes=body.scopes,
            rpm=body.rpm,
        )
        return {
            "key_id": key_id,
            "api_key": raw,
            "tenant_id": body.tenant_id,
            "scopes": body.scopes,
            "rpm": body.rpm,
        }

    @app.put("/v1/admin/tenants/{tenant_id}/mode")
    def set_tenant_mode(
        tenant_id: str,
        body: SetModeRequest,
        principal: ApiPrincipal = Depends(require_principal),
    ) -> dict[str, Any]:
        if not (principal.is_admin or principal.tenant_id == tenant_id):
            raise HTTPException(status_code=403, detail="tenant mismatch")
        if not principal.has_scope("admin") and not principal.has_scope("evaluate"):
            raise HTTPException(status_code=403, detail="insufficient scope")
        app.state.db.set_tenant_mode(tenant_id, body.evaluation_mode)
        return {"tenant_id": tenant_id, "evaluation_mode": body.evaluation_mode}

    @app.get("/v1/admin/tenants/{tenant_id}/mode")
    def get_tenant_mode(
        tenant_id: str,
        principal: ApiPrincipal = Depends(require_principal),
    ) -> dict[str, Any]:
        assert_tenant(principal, tenant_id)
        return {
            "tenant_id": tenant_id,
            "evaluation_mode": app.state.db.get_tenant_mode(tenant_id),
        }

    @app.post("/v1/events")
    def post_events(
        body: EventIngestRequest,
        principal: ApiPrincipal = Depends(require_principal),
    ) -> dict[str, Any]:
        if not principal.has_scope("evaluate"):
            raise HTTPException(status_code=403, detail="evaluate scope required")
        event = EventEnvelope.model_validate(body.model_dump(exclude={"evaluate"}))
        assert_tenant(principal, event.tenant_id)
        if body.evaluate:
            return _run_evaluate(app.state.db, event).model_dump(mode="json")
        try:
            app.state.db.save_event(event)
        except Exception as exc:
            raise HTTPException(status_code=503, detail="event persist failed") from exc
        return {"event_id": event.event_id}

    @app.post("/v1/evaluate")
    def post_evaluate(
        body: EvaluateRequest,
        principal: ApiPrincipal = Depends(require_principal),
    ) -> dict[str, Any]:
        if not principal.has_scope("evaluate"):
            raise HTTPException(status_code=403, detail="evaluate scope required")
        event = _resolve_event(app.state.db, body)
        assert_tenant(principal, event.tenant_id)
        return _run_evaluate(app.state.db, event).model_dump(mode="json")

    @app.post("/v1/shadow/evaluate")
    def post_shadow_evaluate(
        body: ShadowEvaluateRequest,
        principal: ApiPrincipal = Depends(require_principal),
    ) -> dict[str, Any]:
        if not principal.has_scope("evaluate"):
            raise HTTPException(status_code=403, detail="evaluate scope required")
        event = _resolve_event(app.state.db, body)
        assert_tenant(principal, event.tenant_id)
        return _run_shadow_evaluate(
            app.state.db, event, host_friction=body.host_friction
        ).model_dump(mode="json")

    @app.post("/v1/decide")
    def post_decide(
        body: DecideRequest,
        principal: ApiPrincipal = Depends(require_principal),
    ) -> dict[str, Any]:
        if not principal.has_scope("evaluate"):
            raise HTTPException(status_code=403, detail="evaluate scope required")
        event = _resolve_event(app.state.db, body)
        assert_tenant(principal, event.tenant_id)
        event = _enrich_incognia(app.state.db, event)
        event = _enrich_consortium(event)
        try:
            app.state.db.save_event(event)
        except Exception as exc:
            raise HTTPException(status_code=503, detail="event persist failed") from exc
        mode = body.evaluation_mode or app.state.db.get_tenant_mode(event.tenant_id)
        store = _store_for_event(app.state.db, event)
        t0 = time.perf_counter()
        unified = build_unified_decision(
            event,
            store,
            feed_snapshot=body.feed_snapshot,
            program_config=body.program_config,
            cluster_entity_ids=body.cluster_entity_ids,
            scope=body.scope,
            prior_gate_state=body.prior_gate_state,
            evaluation_mode=mode,
        )
        METRICS.observe_evaluate_latency((time.perf_counter() - t0) * 1000.0)
        METRICS.observe_friction(unified.friction.friction.value)
        try:
            if mode == "shadow":
                app.state.db.save_shadow_log(
                    unified.friction, tenant_id=event.tenant_id
                )
            else:
                app.state.db.save_decision(unified.friction, tenant_id=event.tenant_id)
        except Exception as exc:
            raise HTTPException(status_code=503, detail="decision audit failed") from exc
        return unified.model_dump(mode="json")

    @app.get("/v1/decisions/{decision_id}")
    def get_decision(
        decision_id: str,
        principal: ApiPrincipal = Depends(require_principal),
    ) -> dict[str, Any]:
        if not principal.has_scope("read"):
            raise HTTPException(status_code=403, detail="read scope required")
        decision = app.state.db.get_decision(decision_id)
        if decision is None:
            raise HTTPException(status_code=404, detail="decision not found")
        tid = app.state.db.get_decision_tenant(decision_id)
        if tid:
            assert_tenant(principal, tid)
        return decision.model_dump(mode="json")

    @app.post("/v1/challenge_outcomes")
    def post_challenge_outcomes(
        body: ChallengeOutcomeRequest,
        principal: ApiPrincipal = Depends(require_principal),
    ) -> dict[str, Any]:
        if not principal.has_scope("evaluate"):
            raise HTTPException(status_code=403, detail="evaluate scope required")
        tid = app.state.db.get_decision_tenant(body.decision_id)
        if tid:
            assert_tenant(principal, tid)
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
    def get_analytics_summary(
        principal: ApiPrincipal = Depends(require_principal),
    ) -> dict[str, Any]:
        if not principal.has_scope("read"):
            raise HTTPException(status_code=403, detail="read scope required")
        db = app.state.db
        tenant = None if principal.is_admin else principal.tenant_id
        rows = [d.model_dump(mode="json") for d in db.list_decisions(tenant_id=tenant)]
        events_by_id: dict[str, EventEnvelope] = {}
        for d in rows:
            eid = str(d.get("event_id") or "")
            if not eid or eid in events_by_id:
                continue
            event = db.get_event(eid)
            if event is not None:
                events_by_id[eid] = event
        summary = build_summary(rows)
        summary.update(
            build_ops_metrics(
                decisions=rows,
                shadow_logs=db.list_shadow_logs(tenant_id=tenant),
                intel_calls=db.list_intel_calls(),
                challenge_outcomes=db.list_challenge_outcomes(),
                events_by_id=events_by_id,
            )
        )
        shadow_logs = db.list_shadow_logs(tenant_id=tenant)
        summary["shadow_log_count"] = len(shadow_logs)
        loss = summary.get("expected_loss")
        if isinstance(loss, dict):
            summary["expected_loss_sum"] = loss.get("sum") or loss.get("total")
            summary["expected_insult_sum"] = loss.get("insult_sum")
        intel = summary.get("intel_calls")
        if isinstance(intel, dict):
            summary["intel_success_rate"] = intel.get("success_rate")
        ch = summary.get("challenge_conversion")
        if ch is not None:
            summary["challenge_fail_rate"] = (
                None if ch is None else round(1.0 - float(ch), 4)
            )
        summary["soft_floor_count"] = sum(
            1
            for d in rows
            if any(str(r).startswith("floor.soft.") for r in (d.get("reasons") or []))
        )
        summary["hard_floor_count"] = sum(
            1
            for d in rows
            if (d.get("features_snapshot") or {}).get("force_hard_floor")
        )
        if tenant:
            summary["tenant_id"] = tenant
            summary["evaluation_mode"] = db.get_tenant_mode(tenant)
            summary["policy_version"] = (
                rows[-1].get("policy_version") if rows else None
            )
        # p_abuse histogram for dashboard
        hist = {f"{i / 10:.1f}-{(i + 1) / 10:.1f}": 0 for i in range(10)}
        for d in rows:
            p = float(d.get("p_abuse") or 0.0)
            idx = min(9, max(0, int(p * 10)))
            key = f"{idx / 10:.1f}-{(idx + 1) / 10:.1f}"
            hist[key] = hist.get(key, 0) + 1
        summary["p_abuse_histogram"] = hist
        return summary

    @app.get("/v1/export/decisions")
    def export_decisions(
        from_ts: str | None = None,
        to_ts: str | None = None,
        principal: ApiPrincipal = Depends(require_principal),
    ) -> StreamingResponse:
        if not principal.has_scope("export"):
            raise HTTPException(status_code=403, detail="export scope required")
        if principal.is_admin:
            raise HTTPException(
                status_code=400, detail="admin must use tenant-scoped key for export"
            )
        lines = app.state.db.export_decisions_ndjson(
            tenant_id=principal.tenant_id, from_ts=from_ts, to_ts=to_ts
        )

        def gen():
            for line in lines:
                yield line + "\n"

        return StreamingResponse(gen(), media_type="application/x-ndjson")

    @app.get("/v1/export/shadow")
    def export_shadow(
        from_ts: str | None = None,
        to_ts: str | None = None,
        principal: ApiPrincipal = Depends(require_principal),
    ) -> StreamingResponse:
        if not principal.has_scope("export"):
            raise HTTPException(status_code=403, detail="export scope required")
        if principal.is_admin:
            raise HTTPException(
                status_code=400, detail="admin must use tenant-scoped key for export"
            )
        lines = app.state.db.export_shadow_ndjson(
            tenant_id=principal.tenant_id, from_ts=from_ts, to_ts=to_ts
        )

        def gen():
            for line in lines:
                yield line + "\n"

        return StreamingResponse(gen(), media_type="application/x-ndjson")

    static_dir = Path(__file__).resolve().parent.parent.parent / "static"
    if static_dir.is_dir():
        app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")

    return app


_db_path = os.environ.get("LOYALTY_ABUSE_DB", "loyalty_abuse.db")
app = create_app(_db_path)
