# Claim lock — loyalty-abuse standalone

**Date:** 2026-08-06  
**Policy:** `friction_v2_2`  
**Commit gate:** artifacts regenerated this date; pytest green

## What may be claimed

| Claim | Status | Evidence |
|---|---|---|
| **B+** | MET | `artifacts/adversarial_v2_2.json` gates_pass; score diversity gate; points≡score after reconcile |
| **Standalone A+ (technical)** | MET | Dollar knees with full-evaluate floors (`threshold_selection_v2_2.json`); graph ablation lift on `graph_payment_ring` (+1.0 catch); binning calibrator ECE≤0.05 on mixed holdout with score diversity (`calibration_v2_2.json`); shadow reporter + label join + 28d sim pipeline |
| **A++ path (in-repo)** | MET | Incognia adapter fixture+live-gated; challenge outcomes; drift re-eval; ops metrics; consortium stub |
| **Production A+** | NOT MET | Requires ≥4 weeks **live** shadow vs host action + real later-confirmed outcome labels |
| **Production A++** | NOT MET | Requires live Incognia credentials + real challenge labels + weeks of ops |

## Explicit refusals

- Do **not** cite synth-500k as a grade claim.
- Do **not** cite `shadow_four_week_sim*.json` as production A+.
- Do **not** cite Platt ECE≈0 on separable adversarial-only scores (superseded by mixed binning fit).
- Live Incognia: see `docs/compliance/incognia-live.attempt.md`.

## Math honesty notes (`friction_v2_2`)

- Interaction α sum capped ≤0.35; points reconciled to score after clip.
- Correlated multi-window channels use `max`; independent families use `soft_or`.
- Known-device ATO: soft floor, not `force_hard_floor`.
- Cost selection uses `floor_min` from full `evaluate()`.
