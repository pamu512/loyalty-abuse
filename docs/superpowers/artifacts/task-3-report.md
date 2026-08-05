# Task 3 report — cost-optimal threshold selection

## Fix (2026-08-05): frozen pre-selection baseline

**Problem:** `select_thresholds.py` read live `cal["bands"]` as baseline. After `--update-cal`, re-runs compared selected bands against themselves → `improved_on_val: false`, zero cost delta.

**Fix:** Baseline for `improved_on_val` and cost reporting is now frozen at `DEFAULT_BASELINE` (`{24,44,64,84}`) or `--baseline-bands` JSON override. `select_bands` grid/tie-break uses the same frozen baseline. Live cal bands unchanged unless `--update-cal` and val improvement vs frozen baseline.

**Verify:**
```
PYTHONPATH=src python3 -m pytest tests/test_cost_thresholds.py -q   # 1 passed
PYTHONPATH=src python3 scripts/select_thresholds.py --val-seed 7 --report-seed 42 --update-cal
→ improved_on_val: true; val 2975.0 → 2275.0; report 4371.4 → 3514.6
```

Selected bands in `friction_v2_0.json`: `{24,28,48,68}` (unchanged).
