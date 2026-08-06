# Claim lock — loyalty-abuse standalone

**Date:** 2026-08-06  
**Policy:** `friction_v3_0`  
**Program:** Twin-track v2 (product + math) — see `docs/superpowers/specs/2026-08-06-loyalty-abuse-v2-design.md`

## What may be claimed

| Claim | Status | Evidence |
|---|---|---|
| **B+** | MET | `artifacts/adversarial_v3_0.json` gates_pass |
| **Standalone A / A+ (technical)** | MET | Auditor gates + external holdout + deploy/auth product surface |
| **A++ path (in-repo)** | MET | Incognia fixture+live-gated; outcomes; drift; ops dashboard |
| **Production A+** | NOT MET | ≥4 weeks live shadow + real outcome labels required |
| **Production A++** | NOT MET | Live Incognia credentials required |

## v2 product surface

- API keys (SHA-256), tenant isolation, rate limits, NDJSON export
- `/healthz`, `/readyz`, `/metrics`, compose prod profile, `deploy/k8s/`, `docs/ops/runbook-v2.md`
- Ops dashboard (`static/index.html`) with auth + floors/shadow/econ/p histogram
- `POST /v1/decide` unified envelope (economics never denies orders)

## Math (`friction_v3_0`)

- New typologies: `gift_card_drain`, `partner_promo_farm`, `return_to_points`, `trial_referral_farm`
- Deeper graph similarity/density (size≥5), multi-bucket counter aliases, device-intel ATO channel
- Score-path L2 Platt + temporal chrono holdout; outcome-cal fail-closed
- Frozen external pack includes v3 typologies

## Explicit refusals

- Do **not** cite synth-500k as a grade claim.
- Do **not** cite `shadow_four_week_sim*.json` as production A+.
- Production grades remain ops-gated.
- `LOYALTY_ABUSE_AUTH_DISABLED` is test-only — never in production.
