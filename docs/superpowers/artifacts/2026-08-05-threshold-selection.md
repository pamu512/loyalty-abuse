# Threshold selection — friction_v2_0

**Date:** 2026-08-05  
**Protocol:** select knees on validation seed **7** only; report on seed **42** (adversarial + chronological synth). Never retune using seed 42.

## Method

- Labeled rows: adversarial generators (household → `label_abuse=false`; catch slices → `true`).
- Liability: payload money fields if present; else synthetic defaults ($25 abuse / $5 legit).
- Objective: minimize  
  `Σ C_fn·liability·label·miss_fraction[friction] + C_fp[friction]`  
  with `friction = FrictionPolicy(**bands).action_for(score)` (**hard_floor ignored**).
- Candidate grid: `allow_max ∈ {24,28}` (floored at baseline to preserve allow-band goldens / household UX); upper knees search stricter and looser around `{44,64,84}`.
- Report set: adversarial seed 42 + 200 chronological synth journeys (seed 42) — cost only, no re-selection.

## Results

| Set | n | Cost (baseline bands) | Cost (selected) |
|-----|---:|----------------------:|----------------:|
| Val (adv seed 7) | 250 | 2975.0 | **2275.0** |
| Report (adv 42 + chrono 200) | 450 | 4371.4 | **3514.6** |

### Bands

| | allow_max | throttle_max | soft_max | hard_max |
|--|----------:|-------------:|---------:|---------:|
| Baseline | 24 | 44 | 64 | 84 |
| Selected (val seed 7) | 24 | **28** | **48** | **68** |

Selected bands written into `src/loyalty_abuse/calibration/friction_v2_0.json`.

## Gates after update

```
PYTHONPATH=src python3 scripts/adversarial_eval.py --seed 42
→ gates_pass: true (household allow_rate 1.0; catch slices 1.0)
```

Raw artifact: `artifacts/threshold_selection_v2_0.json` (gitignored).

## Notes

- Unconstrained `allow_max` search collapses to 8 under this cost model (`C_fp[block]=1.5` ≪ `$25·C_fn`); floored at 24 by design.
- Catch rates on seed 42 hit 1.0 after tightening upper knees — expected with synthetic liabilities; revisit when real outcome $ labels arrive.
