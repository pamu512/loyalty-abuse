# Claim lock — loyalty-abuse standalone

**Date:** 2026-08-06  
**Policy:** `friction_v2_4`  
**Commit gate:** artifacts regenerated this date; pytest green

## What may be claimed

| Claim | Status | Evidence |
|---|---|---|
| **B+** | MET | `artifacts/adversarial_v2_4.json` gates_pass incl. near-miss + diversity |
| **Standalone A / A+ (technical)** | MET | See auditor-clearance below |
| **A++ path (in-repo)** | MET | Incognia fixture+live-gated; outcomes; drift; ops; external holdout |
| **Production A+** | NOT MET | ≥4 weeks live shadow + real outcome labels required |
| **Production A++** | NOT MET | Live Incognia credentials required (`incognia-live.status`) |

## Auditor clearance (F1–F4) — technical A/A+

| Finding | Clearance evidence |
|---|---|
| F1 p_abuse step | `p_abuse_not_step` bound **0.50**; score-path-only L2 Platt (`platt_v2_4`); friction priors; published `p_abuse_cap=0.97` |
| F2 score≠friction≠p | `ato_p_friction_coherent`: zero allow-band+hard+p≥0.95; ATO p≈0.60 via floor prior 0.38 not 1.0 |
| F3 graph circularity | `graph_payment_ring` catch via score path; ablation regenerable |
| F4 cooperative eval | `nonperfect_catch` ≥2; `ato_score_variance` ≥2; **frozen** `tests/fixtures/external_journeys.json` holdout |

## Residual fixes in `friction_v2_4`

- Score calibrator fits **no-floor-raise** rows only (ATO no longer poisons low-score bins).
- Binning banned on score path; dense-bin clamp if ever re-enabled.
- Extreme-p gate tightened 0.80 → **0.50** (suite actual ~0.37).
- External frozen journey pack + CI test.
- `scripts/fit_calibration_from_labels.py` fail-closed without challenge/clawback provenance.

## Explicit refusals

- Do **not** cite synth-500k as a grade claim.
- Do **not** cite `shadow_four_week_sim*.json` as production A+.
- Production grades remain ops-gated.
- Synth score-path ECE target is **0.15** (near-separable labels); production outcome-fit keeps **0.08**.

## Math notes (`friction_v2_4`)

- Weights: multi_account 0.34 (graph-only can reach soft without floor).
- `friction_p_floor`: throttle 0.08 / soft 0.22 / hard 0.38 / block 0.55.
- `combine_score_and_friction_p` + `p_abuse_cap`.
- Interaction α sum ≤ 0.35; points reconciled after clip.
