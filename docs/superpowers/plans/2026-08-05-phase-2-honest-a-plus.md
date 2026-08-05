# Phase 2 — Honest A / A+ Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship `friction_v2_0` with dollar-aware decisions, tenant graph features + ablation, probability calibration (ECE/Brier), and a shadow reporter + synthetic chronological dry-run — the standalone A / A+ bar from the program spec.

**Architecture:** Extend the Phase 1 engine without breaking the points≡score contract. Monetary payload fields feed `expected_loss_usd` via a published cost model. `FeatureStore` builds a lightweight in-memory tenant graph from observed events and exposes cluster features. A pure-Python Platt calibrator maps `score/100 → p_abuse`. Knees are chosen on a locked validation slice for min expected cost, reported on held-out adversarial + chronological test. Shadow logs recommended vs host action without requiring production weeks in-repo.

**Tech Stack:** Python 3.12, pydantic, pytest, existing SQLite API — **no new dependencies** (no sklearn; Platt + ECE in stdlib math)

**Spec:** `docs/superpowers/specs/2026-08-05-a-plus-plus-program-design.md` (Phase 2)

**Base:** Branch from current Phase 1 tip (`feat/phase-1-honest-b-plus` @ latest). Create `feat/phase-2-honest-a-plus` before Task 1. Phase 1 need not be merged to `main` first.

## Global Constraints

- Core never imports FastAPI, Incognia, or Tarka.
- Only `evaluate()` observes the scored event.
- No `review` friction action.
- Weights still sum to 1.0 ± 1e-6; blend stays `weighted_sum`; `sum(points) ≈ score` ±1 preserved.
- `policy_version` = `friction_v2_0`; bump `SCHEMA_VERSION` to `2` for new Decision fields.
- Cost knees selected on **locked validation** only; report metrics on held-out test — never retune on the report set.
- Label provenance must be documented (red-team / synthetic chronological for this cycle).
- Adversarial B+ suite must remain green (or intentionally retuned once with documented reason).
- Phase 3 (Incognia) out of scope.

## File Structure

| Path | Role |
|---|---|
| `src/loyalty_abuse/calibration/friction_v2_0.json` | Weights, bands, cost model `C_fn`/`C_fp`, graph toggles |
| `src/loyalty_abuse/calibration/__init__.py` | Load v2_0; validate cost + blend |
| `src/loyalty_abuse/schema.py` | Monetary helpers; Decision `expected_loss_usd`, `expected_insult_usd`, `p_abuse` |
| `src/loyalty_abuse/economics.py` | Liability extract + expected cost given friction |
| `src/loyalty_abuse/graph.py` | Build adjacency + cluster features from event list |
| `src/loyalty_abuse/features.py` | Call graph; expose graph_* snapshot keys |
| `src/loyalty_abuse/typologies/` | Optional light use of graph features (multi_account cluster) |
| `src/loyalty_abuse/calibrate.py` | Platt fit + predict; ECE/Brier |
| `src/loyalty_abuse/score.py` | Attach economics + optional calibrated `p_abuse` |
| `src/loyalty_abuse/policy.py` | Unchanged action_for; knees come from cal bands |
| `scripts/select_thresholds.py` | Locked-val cost optimization → writes bands into a candidate JSON |
| `scripts/ablation_graph.py` | Counters-only vs counters+graph on same holdout |
| `scripts/shadow_dry_run.py` | Synthetic chronological shadow report |
| `src/loyalty_abuse_api/app.py` | Shadow evaluate flag / outcome stub table optional |
| `src/loyalty_abuse_api/db.py` | `shadow_decisions` table (recommended friction + host action) |
| `tests/test_economics.py`, `test_graph.py`, `test_calibrate.py`, `test_shadow.py`, … | |
| `artifacts/` | gitignored reports; commit summaries under `docs/` or `artifacts/*.md` if small |

---

### Task 0: Branch + baseline green

**Files:** none (git only)

- [ ] **Step 1: Create branch from Phase 1 tip**

```bash
cd /Users/pamu/Documents/GitHub/loyalty-abuse
git checkout feat/phase-1-honest-b-plus
git checkout -b feat/phase-2-honest-a-plus
PYTHONPATH=src python3 -m pytest -q
PYTHONPATH=src python3 scripts/adversarial_eval.py --seed 42 --out artifacts/adversarial_baseline_p2.json
```

Expected: 65 passed; adversarial `gates_pass: true`.

- [ ] **Step 2: Commit nothing yet** (or empty note in ledger only)

Record BASE SHA in `.superpowers/sdd/task-0-base.sha` if using SDD.

---

### Task 1: Economics — liability fields + expected loss

**Files:**
- Create: `src/loyalty_abuse/economics.py`
- Create: `src/loyalty_abuse/calibration/friction_v2_0.json` (copy v1_2 + cost block; still loadable)
- Modify: `src/loyalty_abuse/calibration/__init__.py` → `_CAL_PATH = friction_v2_0.json`
- Modify: `src/loyalty_abuse/schema.py` — `SCHEMA_VERSION=2`, Decision fields
- Modify: `src/loyalty_abuse/score.py` — fill economics on Decision
- Modify: `contracts/decision.schema.json`
- Create: `tests/test_economics.py`
- Update goldens/tests for `policy_version` / schema_version

**Interfaces:**
- Consumes: event payload, score, friction, cal `cost` block
- Produces:
  - `liability_usd(event) -> float` = sum of `points_liability_usd`, `discount_usd`, `referral_bonus_usd` (missing → 0)
  - `expected_loss_usd(liability, p_abuse, friction) -> float`
  - `expected_insult_usd(friction) -> float` from `C_fp[friction]`
  - Decision fields: `expected_loss_usd`, `expected_insult_usd` (floats)

**Cost model (publish in JSON — use these defaults):**

```json
"cost": {
  "C_fn_per_usd": 1.0,
  "C_fp": {
    "allow": 0.0,
    "throttle": 0.05,
    "soft_challenge": 0.25,
    "hard_challenge": 0.75,
    "block": 1.5
  },
  "miss_fraction": {
    "allow": 1.0,
    "throttle": 0.85,
    "soft_challenge": 0.45,
    "hard_challenge": 0.15,
    "block": 0.0
  }
}
```

Until Task 4 calibration exists, use `p_abuse = score / 100.0` for economics.

```python
# expected_loss ≈ C_fn * liability * p_abuse * miss_fraction[friction]
# expected_insult ≈ C_fp[friction]
# (document units: USD expected per decision)
```

- [ ] **Step 1: Failing tests**

```python
from loyalty_abuse.economics import liability_usd, expected_costs
from loyalty_abuse.schema import EventEnvelope, EventType, FrictionAction

def test_liability_sums_payload():
    e = EventEnvelope(
        event_id="e", tenant_id="t", ts="2026-08-05T00:00:00Z",
        type=EventType.redeem, account_id="a", session_id="s",
        device_id="d", ip="1.1.1.1",
        payload={"points_liability_usd": 10.0, "discount_usd": 2.5, "reward_id": "r", "points": 1, "offer_ids": [], "channel": "app"},
    )
    assert liability_usd(e) == 12.5

def test_missing_money_is_zero():
    e = EventEnvelope(
        event_id="e", tenant_id="t", ts="2026-08-05T00:00:00Z",
        type=EventType.redeem, account_id="a", session_id="s",
        device_id="d", ip="1.1.1.1",
        payload={"reward_id": "r", "points": 1, "offer_ids": [], "channel": "app"},
    )
    assert liability_usd(e) == 0.0

def test_evaluate_sets_expected_fields():
    from loyalty_abuse import evaluate
    from loyalty_abuse.features import FeatureStore
    store = FeatureStore()
    e = EventEnvelope(
        event_id="r1", tenant_id="t", ts="2026-08-05T12:00:00Z",
        type=EventType.redeem, account_id="a", session_id="s",
        device_id="d", ip="1.1.1.1",
        payload={"reward_id": "r", "points": 1, "offer_ids": [], "channel": "app", "points_liability_usd": 20.0},
    )
    d = evaluate(e, store)
    assert d.policy_version == "friction_v2_0"
    assert d.schema_version == 2
    assert d.expected_loss_usd is not None
    assert d.expected_insult_usd is not None
    assert d.expected_insult_usd >= 0.0
```

- [ ] **Step 2: Run — expect FAIL**

- [ ] **Step 3: Implement** `economics.py`, `friction_v2_0.json` (start as copy of v1_2 + cost + `"policy_version": "friction_v2_0"`), wire `evaluate`, update contracts/schema/tests/goldens for version strings.

- [ ] **Step 4: Full pytest + adversarial still green**

```bash
PYTHONPATH=src python3 -m pytest -q
PYTHONPATH=src python3 scripts/adversarial_eval.py --seed 42 --out artifacts/adversarial_v2_0.json
```

- [ ] **Step 5: Commit**

```bash
git commit -m "feat: friction_v2_0 economics fields and expected loss"
```

---

### Task 2: Tenant graph features

**Files:**
- Create: `src/loyalty_abuse/graph.py`
- Modify: `src/loyalty_abuse/features.py`
- Modify: `src/loyalty_abuse/typologies/multi_account.py` (soft-OR in graph cluster confidence)
- Create: `tests/test_graph.py`
- Add sat keys for graph features in `friction_v2_0.json`

**Interfaces:**
- Consumes: list of tenant events ≤ now (from FeatureStore internals)
- Produces snapshot keys:
  - `graph_cluster_size` — distinct accounts in connected component of current account (edges via shared device, phone, pay_hash, email_domain, promo_code)
  - `graph_multi_hop_accounts` — accounts within 2 hops of current account
  - `graph_age_diversity_hours` — stdev or range of account ages (hours) in cluster (0 if size&lt;2)
  - `graph_shared_attr_rarity` — min rarity of linking attrs (e.g. `1/n_accounts_sharing_attr`); high rarity → stronger signal when many share rare device
  - Keep all Phase 1 counters

**Graph build (YAGNI):** Union-Find or BFS adjacency dict in `graph.py`; rebuild from events on each snapshot (O(E) acceptable for Phase 2).

```python
def cluster_features(events: list[EventEnvelope], account_id: str, now: datetime) -> dict[str, float]:
    ...
```

`multi_account` adds channel:

```python
c_graph = sat(float(snapshot.get("graph_cluster_size") or 0), *sat_params("graph_cluster_size"))
c = soft_or([c_dev, c_ip, c_email, c_graph])
```

- [ ] **Step 1: Failing test** — two accounts share device → `graph_cluster_size >= 2`; third account via phone hop → `graph_multi_hop_accounts >= 3` for the seed account.

- [ ] **Step 2: Implement graph + wire features + typology**

- [ ] **Step 3: pytest green; retune adversarial once if needed (document)**

- [ ] **Step 4: Commit** `feat: tenant graph cluster features`

---

### Task 3: Cost-optimal threshold selection (locked validation)

**Files:**
- Create: `src/loyalty_abuse/eval/cost_thresholds.py`
- Create: `scripts/select_thresholds.py`
- Create: `tests/test_cost_thresholds.py`
- Create: `tests/fixtures/threshold_val_labels.json` (small labeled journeys)
- Write: `artifacts/threshold_selection_v2_0.json` (gitignored ok) + committed summary `docs/superpowers/artifacts/2026-08-05-threshold-selection.md` OR `artifacts/threshold_selection_v2_0_summary.md` if artifacts partially tracked — prefer committed summary under `docs/superpowers/artifacts/`

**Interfaces:**
- Consumes: list of `{score, liability_usd, label_abuse: bool}` on validation set; candidate knee grid
- Produces: `bands` dict minimizing `sum(C_fn*liability*label*miss_frac[friction] + C_fp[friction])` where friction = policy.action_for(score) under candidate bands (ignore hard_floor for selection, or apply if present)

**Protocol:**
1. Build validation set from adversarial generators + labeled household (seed=7) — **lock seed 7** for selection.
2. Report set: adversarial seed **42** + separate chronological synth window — **do not** re-select knees using seed 42.
3. Write selected bands into `friction_v2_0.json` only from val seed 7 results.
4. Publish val cost + test cost in summary markdown.

```bash
PYTHONPATH=src python3 scripts/select_thresholds.py --val-seed 7 --report-seed 42 --out artifacts/threshold_selection_v2_0.json
```

- [ ] **Step 1: Unit test** that a toy val set prefers stricter knees when liabilities are huge and labels=1.

- [ ] **Step 2: Implement selector + script; run once; update cal bands if improved; commit code + summary**

- [ ] **Step 3: Commit** `feat: cost-optimal friction threshold selection`

---

### Task 4: Probability calibration (Platt + ECE/Brier)

**Files:**
- Create: `src/loyalty_abuse/calibrate.py`
- Create: `src/loyalty_abuse/calibration/platt_v2_0.json` (fitted `a`, `b` params)
- Modify: `score.py` — set `Decision.p_abuse` from Platt(score/100); economics use `p_abuse`
- Create: `scripts/fit_calibration.py`
- Create: `tests/test_calibrate.py`
- Summary: `docs/superpowers/artifacts/2026-08-05-calibration.md` with ECE, Brier, reliability bins, label provenance

**Interfaces:**
- `fit_platt(scores: list[float], labels: list[int]) -> tuple[float, float]`  # a, b for sigmoid(a*s+b)
- `predict_platt(score: float, a: float, b: float) -> float`
- `ece(probs, labels, n_bins=10) -> float`
- `brier(probs, labels) -> float`

**Labels:** red-team from adversarial catch slices (label=1) + household (label=0) + optional synth; document provenance “synthetic red-team 2026-08-05”. Target ECE ≤ 0.05 on **held-out** seed 42 slice; fit on seed 7 only.

If ECE &gt; 0.05 after one fit: report actual ECE, try isotonic-on-bins (histogram binning calibrator) as fallback still without sklearn; do not fake ≤0.05.

- [ ] **Step 1: Tests for Platt monotonicity + ECE on synthetic well-calibrated data ≈ 0**

- [ ] **Step 2: Implement + fit + wire Decision.p_abuse**

- [ ] **Step 3: Commit** `feat: Platt calibration and ECE/Brier reporting`

---

### Task 5: Graph ablation artifact

**Files:**
- Create: `scripts/ablation_graph.py`
- Create: `tests/test_ablation_graph.py` (smoke: runs small N)
- Summary: `docs/superpowers/artifacts/2026-08-05-graph-ablation.md`

**Protocol:** Same holdout journeys (seed 42 adversarial + labeled). Score with (a) snapshot graph features zeroed / typology graph channel off, (b) full graph. Compare catch_rate / cost. Graph must not hurt household allow_rate by &gt;5pp without documentation.

- [ ] Implement, run, write summary, commit `test: graph feature ablation report`

---

### Task 6: Shadow path + synthetic dry-run

**Files:**
- Modify: `src/loyalty_abuse_api/db.py` — table `shadow_logs(decision_id, event_id, recommended_friction, host_friction, body_json, created_at)`
- Modify: `src/loyalty_abuse_api/app.py` — `POST /v1/shadow/evaluate` returns Decision but also accepts optional `host_friction`; logs both. Live `/v1/evaluate` unchanged (enforcing path).
- Create: `scripts/shadow_dry_run.py` — generate chronological events day-by-day, score shadow, later “confirm” labels from generator truth, emit precision/recall/insult proxy
- Create: `tests/test_shadow.py`
- README: shadow pipeline exists; production A+ needs ≥4 weeks real labels

- [ ] **Step 1: API test** shadow endpoint logs recommended vs host

- [ ] **Step 2: Dry-run script produces JSON report under artifacts/**

- [ ] **Step 3: Commit** `feat: shadow evaluate path and chronological dry-run`

---

### Task 7: Phase 2 closeout

- [ ] Full pytest green
- [ ] Adversarial seed 42 green (or documented retune)
- [ ] README: honest A/A+ language tied to artifacts (economics, ablation, calibration ECE, shadow dry-run) — **do not claim production A+ without 4-week shadow**
- [ ] Update program spec status line to Phase 2 complete (standalone A bar); Phase 3 pending
- [ ] Commit `chore: Phase 2 closeout`
- [ ] Stop — do not start Phase 3 without a Phase 3 plan

---

## Spec coverage (Phase 2)

| Spec item | Task |
|---|---|
| Monetary payload fields | 1 |
| expected_loss / insult + cost model | 1, 3 |
| Cost-optimal knees on locked val | 3 |
| Graph edges + cluster features | 2 |
| Ablation counters vs graph | 5 |
| Platt/isotonic + ECE/Brier | 4 |
| Label provenance documented | 4 |
| Shadow path + synthetic dry-run | 6 |
| No Incognia / no review queue | — |

## Self-review notes

- Task 3 must not peek at seed 42 for knee selection.
- Economics before calibration may use raw score/100; Task 4 switches to `p_abuse`.
- Graph typology weight changes may require one adversarial retune — keep anti-vanity.
- Standalone A+ in-repo ≠ production A+ (4-week shadow) — README must say so.
)
