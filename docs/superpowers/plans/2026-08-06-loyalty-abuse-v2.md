# Loyalty Abuse v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship twin-track v2 — full product (auth/tenant/deploy/dashboard) + full math (`friction_v3_0` typologies, signals, cal, unified envelope).

**Architecture:** `loyalty_abuse` core stays host-agnostic; `loyalty_abuse_api` owns auth, persistence, decide envelope, metrics; static ops console consumes authenticated analytics.

**Tech Stack:** Python 3.12, pydantic v2, FastAPI, uvicorn, SQLite, pytest, Docker/K8s manifests, vanilla JS dashboard.

## Global Constraints

- Core library MUST NOT import FastAPI, Incognia, or Tarka.
- Friction enum is exactly: `allow`, `throttle`, `soft_challenge`, `hard_challenge`, `block` — no `review`.
- Economics path MUST NOT deny orders or set friction `block`.
- No Accertify citations; no QSR naming.
- No production A+/A++ claim without live evidence.
- Full implementations only — no stubs or placeholder scorers.
- Spec: `docs/superpowers/specs/2026-08-06-loyalty-abuse-v2-design.md`

## File map

| Path | Responsibility |
|---|---|
| `src/loyalty_abuse_api/auth.py` | API key hash verify, scopes, bootstrap |
| `src/loyalty_abuse_api/ratelimit.py` | Per-key token bucket |
| `src/loyalty_abuse_api/db.py` | Keys, tenants, export queries |
| `src/loyalty_abuse_api/app.py` | Auth middleware, `/v1/decide`, probes, metrics |
| `src/loyalty_abuse_api/metrics.py` | Prometheus counters/histograms |
| `src/loyalty_abuse/envelope.py` | `UnifiedDecision` builder |
| `src/loyalty_abuse/schema.py` | `UnifiedDecision`, schema bump |
| `src/loyalty_abuse/features.py` | Multi-bucket counters |
| `src/loyalty_abuse/graph.py` | Similarity / multi-hop |
| `src/loyalty_abuse/typologies/*.py` | New + deepened scorers |
| `src/loyalty_abuse/calibration/friction_v3_0.json` | Active policy |
| `static/index.html` | Full ops dashboard |
| `deploy/k8s/*` | K8s manifests |
| `docs/ops/runbook-v2.md` | Ops runbook |

---

### Task 1: P1 Auth, tenancy, rate limits, audit export

**Files:**
- Create: `src/loyalty_abuse_api/auth.py`, `src/loyalty_abuse_api/ratelimit.py`
- Modify: `src/loyalty_abuse_api/db.py`, `src/loyalty_abuse_api/app.py`
- Test: `tests/test_api_auth.py`

**Interfaces:**
- Produces: `verify_bearer(db, authorization_header) -> ApiPrincipal`; `RateLimiter.check(key_id) -> None | raise 429`; `db.create_api_key`, `db.list_decisions_for_tenant`

- [ ] **Step 1:** Write failing tests for 401 without key, 403 cross-tenant, 429 over RPM, NDJSON export.
- [ ] **Step 2:** Implement key table (hash, tenant_id, scopes, rpm), middleware, export routes.
- [ ] **Step 3:** pytest green; commit.

### Task 2: M4 UnifiedDecision + `/v1/decide`

**Files:**
- Create: `src/loyalty_abuse/envelope.py`
- Modify: `src/loyalty_abuse/schema.py`, `src/loyalty_abuse_api/app.py`
- Test: `tests/test_envelope.py`, `tests/test_api_decide.py`

**Interfaces:**
- Produces: `build_unified_decision(event, store, *, economics_feeds, program_config, mode) -> UnifiedDecision`

- [ ] **Step 1:** Failing tests — envelope embeds Decision + economics; `order_decision_untouched` True; economics never block.
- [ ] **Step 2:** Implement builder + `POST /v1/decide`.
- [ ] **Step 3:** pytest green; commit.

### Task 3: P2 Deploy / ops

**Files:**
- Create: `src/loyalty_abuse_api/metrics.py`, `deploy/k8s/deployment.yaml`, `deploy/k8s/service.yaml`, `docs/ops/runbook-v2.md`
- Modify: `src/loyalty_abuse_api/app.py`, `docker-compose.yml`, `Dockerfile`
- Test: `tests/test_health_metrics.py`

- [ ] **Step 1:** Failing tests for `/healthz`, `/readyz`, `/metrics` content-type.
- [ ] **Step 2:** Implement probes, JSON logging middleware, prometheus text, compose prod, k8s, runbook.
- [ ] **Step 3:** pytest green; commit.

### Task 4: M2 Multi-bucket counters + graph depth

**Files:**
- Modify: `src/loyalty_abuse/features.py`, `src/loyalty_abuse/graph.py`, typologies that consume snap
- Test: `tests/test_features.py`, `tests/test_graph.py`

- [ ] **Step 1:** Failing tests for 5m/1h/24h/7d conquer counters; cluster similarity score in snapshot.
- [ ] **Step 2:** Implement; wire into multi_account / ATO soft-OR where applicable.
- [ ] **Step 3:** pytest green; commit.

### Task 5: M1 New typologies

**Files:**
- Create: `src/loyalty_abuse/typologies/gift_card_drain.py`, `partner_promo_farm.py`, `return_to_points.py`, `trial_referral_farm.py`
- Modify: `typologies/__init__.py`, adversarial eval, weights in cal (prep for v3_0)
- Test: `tests/test_typology_v3.py`, adversarial slice tests

- [ ] **Step 1:** Failing unit tests per typology.
- [ ] **Step 2:** Implement scorers + adversarial generators + slice bounds.
- [ ] **Step 3:** pytest green; commit.

### Task 6: P3 Ops dashboard

**Files:**
- Modify: `static/index.html`, analytics endpoints if needed
- Test: `tests/test_dashboard_contract.py` (API shapes dashboard needs)

- [ ] **Step 1:** Extend analytics JSON contract tests for floor/shadow/econ/drift/p_hist.
- [ ] **Step 2:** Full dashboard UI with API key auth.
- [ ] **Step 3:** Manual smoke + pytest; commit.

### Task 7: M3 Calibration realism

**Files:**
- Modify: `scripts/fit_calibration.py` (temporal holdout), `scripts/drift_reeval.py`
- Expand: `tests/fixtures/external_journeys.json`
- Test: external holdout + fit script exit codes

- [ ] **Step 1:** Temporal fit/report windows; expand external pack for new typologies.
- [ ] **Step 2:** Drift artifact path; pytest green; commit.

### Task 8: M5 friction_v3_0 proof

**Files:**
- Create: `friction_v3_0.json`, `platt_v3_0.json`
- Modify: calibration loader, `POLICY_VERSION`, CLAIM_LOCK, README
- Regenerate: adversarial, ablation, calibration, external artifacts

- [ ] **Step 1:** Point active cal to v3_0; fit platt; run suites.
- [ ] **Step 2:** Update CLAIM_LOCK; full pytest; commit.

---

## Interleave reminder

Execute Tasks 1 and 2 first (can parallelize). Then 3 ∥ 4. Then 5. Then 6 ∥ 7. Task 8 last.
