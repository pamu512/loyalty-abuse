# friction_v2_4 — residual risk closeout

> **Privacy:** Letter-grade maturity ratings are private ([`RATINGS_PRIVATE.md`](./RATINGS_PRIVATE.md)). This document uses capability language only.


**Policy:** `friction_v2_4`  
**Pytest:** 175 passed

| Artifact | Result |
|---|---|
| adversarial_v2_4 | gates_pass; extreme frac 0.3667 (&lt; 0.50) |
| calibration_v2_4 | score-path L2 Platt; ECE 0.13 ≤ 0.15 synth target |
| graph_ablation_v2_4 | graph_payment_ring Δ catch +0.78 |
| external_holdout_v2_4 | gates_pass on frozen pack |

## Residuals closed (in-repo)

1. **p extremes** — score-path-only fit + lower friction priors + `p_abuse_cap=0.97`; gate 0.50.
2. **Cooperative-only proof** — frozen external journey pack in CI.
3. **Production label path** — `fit_calibration_from_labels.py` refuses synth-only sets.

## Still open (honest)

- live production / device-intel readiness: live shadow weeks + Incognia credentials.
