# friction_v2_2 — in-repo technical readiness closeout

> **Privacy:** Letter-grade maturity ratings are private ([`RATINGS_PRIVATE.md`](./RATINGS_PRIVATE.md)). This document uses capability language only.


**Date:** 2026-08-06  
**Policy:** `friction_v2_2`

## Changes vs v2_1

- Interaction α budget capped (Σα ≤ 0.35); points reconciled to score after clip
- Multi-account: max across correlated windows; graph multi-hop + rarity wired
- Soft floor `floor.soft.graph_cluster` + adversarial slice `graph_payment_ring`
- Known-device ATO via soft floor (not hard floor); confidence 0.72
- Cost selection uses full-evaluate floor mins
- Calibration: mixed adversarial+chronological; reject step Platt → binning (`platt_v2_2.json`)
- Adversarial score-diversity gate

## Artifacts

| Artifact | Result |
|---|---|
| `artifacts/adversarial_v2_2.json` | gates_pass |
| `artifacts/calibration_v2_2.json` | binning ECE ≈ 0.0036, diversity OK |
| `artifacts/threshold_selection_v2_2.json` | val 1257→615; report 2503→1816 |
| `artifacts/graph_ablation_v2_2.json` | graph_payment_ring catch Δ = +1.0; cost −185 |
| `artifacts/shadow_four_week_sim_v2_2.json` | pipeline only — not live shadow readiness |
| `docs/compliance/RATINGS_PRIVATE.md` | ratings stay private |

## Live readiness

Still **not** claimed in public docs. Internal status lives under `private/` (gitignored).
