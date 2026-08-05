# Incognia adapter

Thin mapper from Incognia login/signup assessments into `IncogniaSignals`.  
Core `loyalty_abuse` never imports this package or the vendor SDK.

## Modes

| Mode | When | `source` |
|---|---|---|
| Fixture / replay | Env creds absent (default offline) | `fixture` |
| Live | `INCOGNIA_CLIENT_ID`, `INCOGNIA_CLIENT_SECRET`, `INCOGNIA_POLICY_ID` set and optional extra installed | `live` |
| Unavailable | Live call fails / SDK missing when required path degrades | `unavailable` |

Live client (`fetch_signals`) is Task 2 — this package currently ships normalize + pinned fixtures only.

## Env vars (live; Task 2)

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
