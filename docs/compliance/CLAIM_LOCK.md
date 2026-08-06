# Claim lock — loyalty-abuse standalone

**Date:** 2026-08-06  
**Policy:** `friction_v2_3`  
**Commit gate:** artifacts regenerated this date; pytest green (169)

## What may be claimed

| Claim | Status | Evidence |
|---|---|---|
| **B+** | MET | `artifacts/adversarial_v2_3.json` gates_pass incl. near-miss + diversity |
| **Standalone A / A+ (technical)** | MET | See auditor-clearance below |
| **A++ path (in-repo)** | MET | Incognia fixture+live-gated; outcomes; drift; ops |
| **Production A+** | NOT MET | ≥4 weeks live shadow + real outcome labels required |
| **Production A++** | NOT MET | Live Incognia credentials required (`incognia-live.status`) |

## Auditor clearance (F1–F4) — technical A/A+

| Finding | Clearance evidence |
|---|---|
| F1 p_abuse step | `p_abuse_not_step` gate: frac extremes &lt; 0.80; friction-conditional noisy-OR prior; smoothed/L2 calibration (`calibration_v2_3.json`) |
| F2 score≠friction≠p | `ato_p_friction_coherent`: zero allow-band+hard+p≥0.95; ATO p≈0.91 via floor prior 0.50 not 1.0 |
| F3 graph circularity | `graph_payment_ring` catch via score path (multi w=0.34); graph soft floor removed; ablation Δ catch = +0.78 |
| F4 cooperative eval | `nonperfect_catch` ≥2 slices &lt;1.0; `ato_score_variance` ≥2; `pattern_block_rate` 0.35 (headroom) |

## Explicit refusals

- Do **not** cite synth-500k as a grade claim.
- Do **not** cite `shadow_four_week_sim*.json` as production A+.
- Production grades remain ops-gated.

## Math notes (`friction_v2_3`)

- Weights: multi_account 0.34 (graph-only can reach soft without floor).
- `combine_score_and_friction_p` published `friction_p_floor`.
- Interaction α sum ≤ 0.35; points reconciled after clip.
- Correlated windows → max; ATO urgency boost for score variance.
