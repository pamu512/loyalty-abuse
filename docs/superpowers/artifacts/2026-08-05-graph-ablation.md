# Graph feature ablation — counters vs counters+graph

**Date:** 2026-08-05  
**Protocol:** same adversarial holdout journeys (seed **42**, N=50/slice). Score (a) snapshot `graph_*` zeroed / typology graph channel off, (b) full graph. Compare catch_rate / labeled cost. Gate: household `allow_rate` must not drop by more than **5pp** with graph.

## Method

- Journeys: `loyalty_abuse.eval.adversarial.GENERATORS` (household labeled legit; catch slices labeled abuse).
- Counters-only: after `FeatureStore.snapshot`, zero `graph_cluster_size`, `graph_multi_hop_accounts`, `graph_age_diversity_hours`, `graph_shared_attr_rarity` before typologies run.
- Counters+graph: production `evaluate()` path unchanged.
- Friction / catch: ≥ `soft_challenge` = catch; `allow` = allow. Cost: locked `friction_v2_0` bands + cost model via `total_labeled_cost` (hard_floor ignored).

## Results (seed 42)

| Mode | n | Labeled cost | household allow_rate |
|------|--:|-------------:|---------------------:|
| Counters-only | 250 | 2275.0 | 1.0 |
| Counters+graph | 250 | 2275.0 | 1.0 |

### Per-slice rates

| Slice | Metric | Counters-only | +graph | Δ (graph − counters) |
|-------|--------|-------------:|-------:|---------------------:|
| household_fp | allow_rate | 1.0 | 1.0 | 0.0 |
| device_rotation | catch_rate | 1.0 | 1.0 | 0.0 |
| slow_multi_acct | catch_rate | 1.0 | 1.0 | 0.0 |
| sequential_promo | catch_rate | 1.0 | 1.0 | 0.0 |
| ato_known_device | catch_rate | 1.0 | 1.0 | 0.0 |

- **Household allow drop:** 0.0pp (gate ≤5pp) → **pass**
- **Labeled cost Δ:** 0.0

## Interpretation

Graph features are non-zero on this holdout (e.g. household max cluster 3; `slow_multi_acct` max cluster 5 and emits `multi_acct.graph_cluster`). Soft-OR over device/IP/email already saturates multi-account confidence on catch slices, so zeroing graph does not move score, catch_rate, household allow_rate, or labeled cost. Ablation therefore shows **no harm** and **no incremental catch** on this synthetic set — not a claim that graph is useless under production labels or denser tenant graphs.

## Reproduce

```bash
PYTHONPATH=src python3 scripts/ablation_graph.py --seed 42 --out artifacts/graph_ablation_v2_0.json
pytest tests/test_ablation_graph.py -q
```

Raw artifact: `artifacts/graph_ablation_v2_0.json` (gitignored).
