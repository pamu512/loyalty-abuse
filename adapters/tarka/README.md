# Tarka host adapter (optional, not shipped in v1)

This directory is reserved for a thin mapper between Tarka (or similar host orchestrators) and the standalone `loyalty_abuse` library. **No Python code ships here in v1** — core scoring stays host-agnostic.

## Event mapping

Host evaluate payloads should be translated into `EventEnvelope` (see `contracts/event-envelope.schema.json`):

| Host concept | `EventEnvelope` field |
|---|---|
| Event identifier | `event_id` |
| Tenant / brand | `tenant_id` |
| Timestamp | `ts` (ISO-8601 UTC) |
| Journey step | `type` (`signup`, `login`, `redeem`, …) |
| Guest identifiers | `account_id`, `session_id`, `device_id`, `ip` |
| Step-specific data | `payload` (type-dependent) |

The adapter owns field renaming and defaults; `loyalty_abuse` never imports Tarka types.

## Decision mapping

`evaluate()` returns a `Decision` (see `contracts/decision.schema.json`). Map `Decision.friction` onto host action enums:

| `friction` | Typical host action |
|---|---|
| `allow` | Proceed |
| `throttle` | Rate-limit or slow path |
| `soft_challenge` | Step-up (CAPTCHA, OTP) |
| `hard_challenge` | Strong verification |
| `block` | Deny / hard stop |

Pass through `score`, `reasons`, `typologies`, `policy_version`, and `schema_version` for audit and replay.

## Integration modes

- **In-process:** `from loyalty_abuse import evaluate` with a host-managed `FeatureStore`.
- **HTTP:** `POST /v1/evaluate` with `{ "event": { … } }` or `{ "event_id": "…" }` against the standalone API.

When a Tarka adapter is added, its tests live under `adapters/tarka/tests/` and do not gate the core library.
