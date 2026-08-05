# Probability calibration — Platt + ECE/Brier

**Date:** 2026-08-05  
**Label provenance:** synthetic red-team 2026-08-05  
**Protocol:** fit on adversarial+household seed **7** only; ECE/Brier on held-out seed **42**. Never refit using seed 42.

## Labels

| Slice | `label_abuse` | Source |
|-------|:-------------:|--------|
| `household_fp` | 0 | adversarial generator |
| `device_rotation` | 1 | adversarial catch |
| `slow_multi_acct` | 1 | adversarial catch |
| `sequential_promo` | 1 | adversarial catch |
| `ato_known_device` | 1 | adversarial catch |

n = 50 journeys/slice → 250 fit, 250 report. No production outcome labels in this cycle.

## Method

- Input score: `score/100` (integer Decision score scaled to [0, 1]).
- Primary: pure-Python Platt MLE — `p = sigmoid(a·s + b)` (Newton; no sklearn).
- If held-out ECE > 0.05: fit equal-width histogram binning on seed 7 and compare; report actual ECE (do not claim ≤0.05 if unmet).
- Wired: `Decision.p_abuse`; economics use calibrated `p_abuse` (not raw `score/100`).

## Held-out results (seed 42)

| Calibrator | ECE (10 bins) | Brier |
|------------|--------------:|------:|
| Platt | **5.66e-11** | **8.08e-21** |
| Binning fallback | not needed (Platt ECE ≤ 0.05) | — |

**Selected:** `method=platt` → `src/loyalty_abuse/calibration/platt_v2_0.json`  
`a ≈ 412.42`, `b ≈ -22.78`

### Reliability bins (Platt, seed 42)

| Bin | n | mean confidence | empirical accuracy |
|----:|--:|----------------:|-------------------:|
| [0.0, 0.1) | 50 | ~0 | 0.0 |
| [0.1, 0.9) | 0 | — | — |
| [0.9, 1.0] | 200 | ~1 | 1.0 |

Scores on this red-team set are near-separable (household low, catch slices high), so Platt collapses toward a step and ECE/Brier approach zero. That is honest on this synthetic slice — not a claim about production calibration.

## Reproduce

```bash
PYTHONPATH=src python3 scripts/fit_calibration.py --fit-seed 7 --report-seed 42
```

Raw metrics: `artifacts/calibration_v2_0.json` (gitignored).
