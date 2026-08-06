# QSR Loyalty Abuse — Design

**Date:** 2026-08-04  
**Status:** Draft for implementation  
**Approach:** Rules-first explainable score with tiered friction (no review queue)

## Goal

Detect and interrupt QSR loyalty / promotion abuse across the guest journey with an **explainable score** and **tiered friction up to block**. Ship a **standalone** system that runs on its own and can also be embedded or called by hosts such as Tarka without depending on them.

## Non-goals (v1)

- Analyst review / case-desk disposition as a primary product path
- Production ML training loop (hook only)
- Hard dependency on Tarka, Neo4j, Redis, or any host platform
- Payment-fraud chargeback modeling (adjacent; out of scope unless it feeds loyalty ATO signals)

## Design principles

1. **Standalone-first.** Core scoring and friction policy are a pure library. The HTTP service is one adapter; Tarka (or any host) is another. Hosts never required to run tests or score offline.
2. **Explainable by default.** Every decision returns score + typology breakdown + reason codes. No opaque score.
3. **Friction, not review.** Outcomes are only: `allow` → `throttle` → `soft_challenge` → `hard_challenge` → `block`.
4. **Audit before action.** Persist the decision (with frozen features) before returning success to a caller.
5. **Journey-wide signals.** Abuse is scored across signup, login, referral, offer, redeem, and checkout — not payment alone.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│ Hosts (optional)                                            │
│  • Standalone FastAPI service                               │
│  • Tarka Decision API / orchestrator adapter (thin)         │
│  • Any other HTTP or in-process caller                      │
└───────────────────────────┬─────────────────────────────────┘
                            │ EventEnvelope / EvaluateRequest
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ loyalty_abuse (library)                                     │
│  1. Ingest / normalize events                               │
│  2. Feature engine (velocity, linkage, lifecycle, promo, ATO)│
│  3. Typology scorers → additive explainable score           │
│  4. Friction policy → action                                │
│  5. Build Decision (features snapshot + reasons + friction) │
└───────────────────────────┬─────────────────────────────────┘
                            │ Decision (in-memory)
            ┌───────────────┼───────────────┐
            ▼               ▼               ▼
     Event store      Decision audit   Analytics / offline eval
     (SQLite v1,      (SQLite v1,      (notebook + summary API)
      API adapter)     API adapter;
                       required before
                       HTTP 200)
```

Library `evaluate()` returns a `Decision`; it does not open sockets or databases. Persistence and fail-closed audit are adapter responsibilities (standalone API today; Tarka or other hosts later).

**Package layout (intended):**

| Path | Role |
|---|---|
| `src/loyalty_abuse/` | Pure library: schema, features, typologies, policy, score |
| `src/loyalty_abuse_api/` | FastAPI adapter + SQLite persistence |
| `adapters/tarka/` | Optional thin mapper (event/decision ↔ host shapes); not imported by core |
| `notebooks/` | Offline eval |
| `frontend/` or `static/` | Minimal analytics dashboard |
| `tests/` | Unit + golden + API contract |

Core must not import FastAPI, Tarka, or dashboard code.

## Integration contract (standalone ↔ Tarka ↔ others)

Stable JSON contracts live in `contracts/`:

- `event-envelope.schema.json`
- `evaluate-request.schema.json`
- `decision.schema.json`

**In-process:** `from loyalty_abuse import evaluate`  
**HTTP:** `POST /v1/events`, `POST /v1/evaluate`  
**Tarka (optional later):** adapter translates host evaluate payloads into `EventEnvelope` and maps `Decision.friction` onto host action enums. Core stays unaware of Tarka types.

Versioning: `policy_version` + `schema_version` on every decision for replay.

## Event schema

**Common envelope:** `event_id`, `tenant_id`, `ts`, `type`, `account_id`, `session_id`, `device_id`, `ip`, optional `email`, `phone`, `payment_instrument_hash`, plus type-specific `payload`.

| type | payload highlights |
|---|---|
| `signup` | email, phone, referral_code, utm/source |
| `login` | success, new_device, geo |
| `profile_update` | fields_changed[] |
| `referral` | referrer_id, referee_id |
| `offer_enroll` | offer_id, campaign_id |
| `redeem` | reward_id, points, offer_ids[], channel |
| `checkout` | order_id, amount, promo_codes[], loyalty_applied[] |

Evaluate runs on the triggering event (`signup`, `referral`, `redeem`, `checkout`, and high-risk `login` / `profile_update` chains). Features used for the decision are frozen into the audit row.

## Feature families

| Family | Examples |
|---|---|
| Velocity | redemptions/signups/logins per account/device/IP/code in 5m / 1h / 24h |
| Linkage | distinct accounts sharing device / IP / email-root / phone / payment; referral pair shared-attr flags |
| Lifecycle | account age; minutes signup→first redeem; profile-change→redeem gap |
| Promo shape | stacked offer count; discount depth; code unique-user concentration; burst vs campaign start |
| ATO sequence | unfamiliar device/geo login → profile change → redeem within a short window |

v1 feature store: in-process counters + link index backed by SQLite. No external Redis/Neo4j required.

## Typologies

Score is **0–100**, additive, capped. Each typology emits `{id, points, reasons[]}`.

| typology | What it catches | Example reason codes |
|---|---|---|
| `multi_account` | Duplicate accounts farming welcome/birthday/referral offers | `multi_acct.shared_device_cluster`, `multi_acct.email_alias_burst` |
| `referral_self_deal` | Self-referral or accomplice pairs sharing device/IP/payment | `referral.shared_device`, `referral.shared_payment` |
| `promo_stack` | Stacking offers beyond intended economics | `promo.stack_depth`, `promo.discount_depth` |
| `bot_redeem` | Sub-human signup/redeem velocity and cadence | `bot.redeem_velocity`, `bot.signup_velocity` |
| `code_leak` | Limited codes leaked to deal sites / wide unique-user spike | `code.unique_user_spike`, `code.source_cluster` |
| `ato_redeem` | Login anomaly → profile edit → fast redeem/transfer | `ato.login_profile_redeem_chain` |

Point bands are configurable per typology; defaults land typical hits in the 15–45 range so combinations climb the friction ladder naturally.

## Friction policy

No `review` action in the product path.

| score | action | meaning |
|---|---|---|
| 0–24 | `allow` | proceed |
| 25–44 | `throttle` | delay / rate-limit claim or redeem |
| 45–64 | `soft_challenge` | CAPTCHA / OTP |
| 65–84 | `hard_challenge` | re-auth + hold reward until verified |
| 85–100 | `block` | deny claim/redeem |

**Hard overrides (optional, policy-flagged):** confirmed ATO chain or extreme bot velocity may force floor ≥ `hard_challenge` even if the raw sum is lower.

Thresholds and overrides are tenant-overridable; `policy_version` is recorded on every decision.

## Decision response (explainable)

```json
{
  "decision_id": "dec_…",
  "event_id": "evt_…",
  "score": 72,
  "friction": "hard_challenge",
  "reasons": ["ato.login_profile_redeem_chain", "multi_acct.shared_device_cluster"],
  "typology_breakdown": [
    {"id": "ato_redeem", "points": 40, "reasons": ["ato.login_profile_redeem_chain"]},
    {"id": "multi_account", "points": 32, "reasons": ["multi_acct.shared_device_cluster"]}
  ],
  "policy_version": "friction_v1",
  "schema_version": 1
}
```

## API (standalone service)

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/v1/events` | Ingest event; optional `evaluate: true` |
| `POST` | `/v1/evaluate` | Score from `event_id` or inline event |
| `GET` | `/v1/decisions/{decision_id}` | Audit replay |
| `GET` | `/v1/analytics/summary` | Friction mix, score hist, top reasons, typology rates |

**Fail-closed audit:** evaluate persists the full decision record before HTTP 200. Persist failure → 503, no friction action returned as success.

## Offline eval & demo

- Seed generator for the six typology patterns (plus clean traffic).
- Notebook/script over events + decisions: friction distribution, reason coverage, threshold sweeps, fixture precision proxies.
- Minimal dashboard bound to `/v1/analytics/summary`.

## Testing

- Unit tests per typology scorer (edge cases: empty linkage, single account, burst windows).
- Golden fixtures for each friction tier (`allow` / `throttle` / `soft_challenge` / `hard_challenge` / `block`).
- Library tests run with **no** API server.
- API contract tests: audit-before-200; schema validation on request/response.
- Adapter tests (when Tarka adapter exists) stay under `adapters/tarka/tests/` and do not gate core.

## Stack (v1)

- Python 3.12
- FastAPI (API adapter only)
- SQLite for events + decisions
- pytest
- `docker compose up` for API + static dashboard

## Success criteria

1. Standalone: `docker compose up` (or `uvicorn`) accepts events and returns explainable friction decisions with no host platform installed.
2. Library-only: `evaluate()` works in-process from fixtures with identical scores to HTTP for the same frozen features.
3. All six typologies emit at least one golden reason path.
4. Friction ladder has golden coverage for every tier; no `review` action exists in the enum.
5. Optional Tarka adapter can be added later without changing core schemas.

## Open follow-ups (post-v1)

- Bounded ML score delta (hybrid) behind a feature flag
- External counter store (Redis) for multi-instance deploy
- Richer graph backend if linkage volume outgrows SQLite
- Deeper Tarka Decision API / typology pack mirror (adapter only)
