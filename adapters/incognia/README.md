# Incognia adapter

Thin mapper from Incognia login/signup assessments into `IncogniaSignals`.  
Core `loyalty_abuse` never imports this package or the vendor SDK.

## Modes

| Mode | When | `source` |
|---|---|---|
| Fixture / replay | Env creds absent **and** caller opts in (adapter unit tests, or API payload `incognia_fixture` / `incognia_use_fixture=true`) | `fixture` |
| Live | `INCOGNIA_CLIENT_ID`, `INCOGNIA_CLIENT_SECRET`, `INCOGNIA_POLICY_ID` set and optional extra installed | `live` |
| Unavailable | Live call fails / SDK missing / API path has token but no env creds (no silent fixture) | `unavailable` |

`fetch_signals` still loads a fixture when env creds are absent (handy for direct adapter tests). The **API enrich path does not** call that fallback unless the payload sets `incognia_fixture` or `incognia_use_fixture=true`; otherwise missing creds → `source=unavailable`.

## Fail-closed / force floor

When `incognia_required=true` on redeem/checkout and intel is unavailable (error, missing creds, or **missing request token**), the API sets `device_intel_force_block=true`.

That flag forces a **hard floor** via policy: friction ≥ `hard_challenge` (not a literal `block`). Hosts should treat it as strong verification / hold, same ladder as other hard floors — `block` only if score/policy maps there after the floor.

## Env vars (live)

- `INCOGNIA_CLIENT_ID`
- `INCOGNIA_CLIENT_SECRET`
- `INCOGNIA_POLICY_ID`

## Fixtures

Pinned snake_case JSON under `fixtures/` (shape from public SDK docs):

- `login_low_risk.json` — clean device, `risk_assessment: low_risk`
- `login_high_risk.json` — `probable_root` + `emulator`, `risk_assessment: high_risk`

## Field mapping

| Raw assessment path | `IncogniaSignals` field | Notes |
|---|---|---|
| `risk_assessment` | `risk_assessment` | `low_risk` / `high_risk` / `unknown_risk`; unknown/missing → `unknown_risk` |
| `evidence.device_integrity.probable_root` | `tamper_suspected` | Root/jailbreak proxy for tamper |
| `evidence.device_integrity.emulator` | `emulator` | Default `false` if absent |
| `evidence.device_integrity.gps_spoofing` | `gps_spoofing` | Default `false` if absent |
| `evidence.location_services.location_permission_enabled` | `location_permission_enabled` | `None` if evidence missing |
| `evidence.device_fraud_reputation` | `device_fraud_reputation` | e.g. `allowed`, `unknown` |
| `evidence.known_account` | `known_account` | `None` if evidence missing |
| `id` | `raw_id` | Assessment resource id |
| *(caller)* | `source` | `fixture` \| `live` \| `unavailable` |

Not mapped (kept only in raw fixtures for fidelity): `from_official_store`, `location_sensors_enabled`.
