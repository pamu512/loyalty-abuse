# Loyalty Abuse v2 — Twin-Track Design

**Date:** 2026-08-06  
**Status:** Approved for implementation  
**Policy base:** `friction_v2_4` → target **`friction_v3_0`**  
**Approach:** A — Product track + Math track, interleaved, full implementations only

## Goal

Ship a production-ready standalone loyalty-abuse service (auth, tenancy, deploy/ops, ops dashboard) interleaved with a complete catch/math upgrade: new typologies, deeper signals, calibration realism, and a unified friction + economics decision envelope — without claiming live production / device-intel readiness until live evidence exists.

## Non-goals

- live production / device-intel readiness claim without ≥4 weeks live shadow + real outcome labels + Incognia credentials.
- GNN-first graph ML (v2 deepens deterministic graph features only).
- Review queue / `review` friction action.
- Economics path denying orders / setting friction `block`.
- Accertify citations or QSR product naming.
- New frontend framework (ops console stays vanilla JS static).

## Locked decisions

| Decision | Choice |
|---|---|
| Sequencing | Interleaved twin-track |
| Completeness | Full implementation per track item — no thin slices / stubs |
| Next policy | `friction_v3_0` |
| Auth | Bearer API keys (SHA-256 hashed), tenant-bound |
| Rate limit | In-process token bucket per key |
| Envelope | `UnifiedDecision` via `POST /v1/decide`; legacy evaluate kept |
| Dashboard | Full ops console on `static/` |
| Core boundary | `loyalty_abuse` never imports FastAPI / Incognia / Tarka |

## Architecture

```
Host → API key + tenant + rate limit → loyalty_abuse_api
        → FeatureStore (multi-bucket counters + graph)
        → evaluate() + evaluate_loyalty_economics()
        → UnifiedDecision
        → shadow_logs | decisions (by tenant evaluation_mode)
Ops dashboard ← authenticated analytics / ops metrics
```

### Product track (P)

1. **P1 Auth / tenancy / rate limits / audit export** — Bearer keys, tenant isolation, RPM limits, NDJSON export.
2. **P2 Deploy / ops** — `/healthz`, `/readyz`, JSON logs, Prometheus `/metrics`, compose prod, `deploy/k8s/`, runbook.
3. **P3 Ops dashboard** — Full console: friction, floors, insult/loss, shadow vs live, economics, drift, p histogram, policy version.

### Math track (M)

1. **M1 New typologies** — `gift_card_drain`, `partner_promo_farm`, `return_to_points`, `trial_referral_farm`.
2. **M2 Deeper signals** — Multi-bucket counters; graph hops / similarity; device intel soft-OR; promo lifecycle.
3. **M3 Calibration realism** — Temporal holdout; expanded external pack; drift artifact; outcome-cal fail-closed.
4. **M4 Unified envelope** — `UnifiedDecision` + `/v1/decide`; economics cannot deny.
5. **M5 Policy proof** — `friction_v3_0` + `platt_v3_0`; regenerate artifacts; update private claim lock locally (not committed).

## Acceptance

| Gate | Criterion |
|---|---|
| Auth | Unauthenticated evaluate → 401; cross-tenant → 403; over RPM → 429 |
| Envelope | `/v1/decide` returns friction + economics; economics never sets order deny |
| Deploy | Probes + metrics + k8s manifests + runbook present |
| Dashboard | Authenticated views for all ops surfaces listed in P3 |
| Typologies | Each new typology has scorer, weight, adversarial slice, external freeze |
| Cal | Score-path Platt; outcome path refuses synth-only; temporal holdout script |
| Proof | Adversarial + external + ablation gates_pass under `friction_v3_0` |
| Claims | Live production / device-intel readiness not published; status only in `private/` |

## Research appendix (platform patterns)

| Pattern | Sources |
|---|---|
| Rules + shadow→live | [DoorDash rules engine](https://careersatdoordash.com/blog/doordash-fraud-insights-from-building-a-real-time-rules-engine/), [Uber Mastermind](https://www.uber.com/us/en/blog/mastermind/), [Grab Griffin](https://engineering.grab.com/griffin) |
| Counters | [Grab Trust Counter](https://engineering.grab.com/using-grabs-trust-counter-service-to-detect-fraud-successfully) |
| Graph rings | [Grab Graph Networks](https://engineering.grab.com/graph-networks), [Stripe similarity clustering](https://stripe.com/blog/similarity-clustering) |
| Challenges | [Uber risk challenges](https://www.uber.com/us/en/blog/stopping-uber-fraudsters-through-risk-challenges/), [Lyft](https://eng.lyft.com/stopping-fraudsters-by-changing-products-452240f2d2cc) |
| Promo / multi-account | [Stripe promo abuse](https://stripe.com/resources/more/account-and-promotion-abuse), Amazon Fraud Detector loyalty templates |
| Anomaly / drift | [DoorDash anomaly](https://careersatdoordash.com/blog/doordash-anomaly-detection-platform-to-catch-fraud-trends/), [Uber RADAR](https://www.uber.com/us/en/blog/project-radar-intelligent-early-fraud-detection/) |

## Global constraints

- Core library: no FastAPI / Incognia / Tarka imports.
- Friction enum unchanged; no `review` action.
- Economics never denies the order.
- No Accertify / QSR naming.
- No live shadow readiness claim without live shadow + real labels.
- Full implementation per task; no stubs / TODOs / placeholder scorers.
