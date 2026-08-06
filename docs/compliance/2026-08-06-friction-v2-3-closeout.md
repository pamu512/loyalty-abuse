# friction_v2_3 — in-repo technical readiness closeout

> **Privacy:** Letter-grade maturity ratings are private ([`RATINGS_PRIVATE.md`](./RATINGS_PRIVATE.md)). This document uses capability language only.


Clears third-party audit F1–F4 for **in-repo technical readiness**. Live production / device-intel readiness still refused.

## Evidence

| Artifact | Result |
|---|---|
| adversarial_v2_3 | gates_pass (near-miss, p_abuse, ATO variance, graph) |
| calibration_v2_3 | meets ECE; mixed holdout |
| graph_ablation_v2_3 | graph_payment_ring Δ catch +0.78 |
| threshold_selection_v2_3 | floor-aware cost improved on val/report |

## Not claimed

Live production / device-intel readiness — internal status under `private/` only; see [`RATINGS_PRIVATE.md`](./RATINGS_PRIVATE.md).
