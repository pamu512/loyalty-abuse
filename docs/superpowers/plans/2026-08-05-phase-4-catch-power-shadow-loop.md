# Phase 4 — Catch-Power + Shadow/Label Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship `friction_v2_1` (published interaction terms + soft floors) so pattern abuse can reach soft+ honestly, then ship the shadow→label→retrain loop, 4-week playbook, 28-day sim, and floor-attribution ops metrics.

**Architecture:** Part A extends blend in `score.py` with cal-driven `interactions[]` and applies soft floors in `floors.py` after band mapping. Part B adds label-join / retrain scripts, playbook, sim, and analytics attribution — no historical decision rewrites.

**Tech Stack:** Python 3.12, existing pydantic/pytest/FastAPI/SQLite — no new deps

**Spec:** `docs/superpowers/specs/2026-08-05-phase-4-catch-power-shadow-loop-design.md`

**Base:** Create `feat/phase-4-catch-power-shadow` from `feat/phase-3-a-plus-plus` tip.

## Global Constraints

- Core never imports FastAPI, Incognia, or Tarka.
- Only `evaluate()` observes the scored event.
- No `review` action; no `max_weight_normalize`.
- Weights sum to 1.0 ± 1e-6; interaction α’s published in JSON.
- `sum(typology points + ix points) ≈ score` ±1.
- Soft floors raise friction only; score/`p_abuse`/economics use numeric score.
- Anti-vanity adversarial rules stay; household allow_rate ≥ 0.85.
- Retrain refuses ECE > 0.05 without `--force`.
- Sim/playbook ≠ production 4-week claim.
- Part B starts only after Part A adversarial green.

## File Structure

| Path | Role |
|---|---|
| `src/loyalty_abuse/calibration/friction_v2_1.json` | v2_0 copy + `interactions` + `soft_floors` |
| `src/loyalty_abuse/calibration/__init__.py` | Load v2_1; validate interactions + soft_floors |
| `src/loyalty_abuse/interactions.py` | Compute ix contributions from confidences |
| `src/loyalty_abuse/floors.py` | Soft (+ hard force) friction elevation |
| `src/loyalty_abuse/score.py` | Blend + floors wiring |
| `src/loyalty_abuse/schema.py` | `POLICY_VERSION = friction_v2_1` |
| `src/loyalty_abuse/eval/adversarial.py` | Claim language + floor-aware catch notes |
| `scripts/build_label_set.py` | Join decisions/outcomes/clawbacks |
| `scripts/retrain_calibration.py` | ECE-gated Platt write |
| `scripts/shadow_four_week_sim.py` | 28-day synthetic dry-run |
| `docs/superpowers/playbooks/2026-08-05-shadow-four-week.md` | Ops playbook |
| `src/loyalty_abuse_api/analytics.py` | Floor-vs-score attribution |
| `tests/test_interactions.py`, `test_floors.py`, `test_label_set.py`, `test_retrain_calibration.py`, … | |

---

## Part A — Catch-power

### Task 0: Branch + baseline green

- [ ] Create branch; pytest + adversarial green on Phase 3 tip.

```bash
cd /Users/pamu/Documents/GitHub/loyalty-abuse
git checkout feat/phase-3-a-plus-plus
git checkout -b feat/phase-4-catch-power-shadow
PYTHONPATH=src:. python3 -m pytest -q
PYTHONPATH=src:. python3 scripts/adversarial_eval.py --seed 42 --out artifacts/adversarial_p4_baseline.json
```

---

### Task 1: `friction_v2_1.json` + loader validation

**Files:** create `friction_v2_1.json`; update `calibration/__init__.py`; `tests/test_calibration.py`

Copy `friction_v2_0.json` and add:

```json
"policy_version": "friction_v2_1",
"interactions": [
  {"id": "ix.multi_promo", "a": "multi_account", "b": "promo_stack", "alpha": 0.22},
  {"id": "ix.multi_code", "a": "multi_account", "b": "code_leak", "alpha": 0.18},
  {"id": "ix.bot_multi", "a": "bot_redeem", "b": "multi_account", "alpha": 0.15},
  {"id": "ix.promo_code", "a": "promo_stack", "b": "code_leak", "alpha": 0.15}
],
"soft_floors": [
  {
    "id": "slow_multi",
    "typology": "multi_account",
    "min_confidence": 0.7,
    "feature": "accounts_on_device_7d",
    "min_feature": 4,
    "min_friction": "soft_challenge",
    "reason": "floor.soft.slow_multi"
  },
  {
    "id": "promo_stack",
    "typology": "promo_stack",
    "min_confidence": 0.6,
    "feature": "stack_depth",
    "min_feature": 4,
    "min_friction": "soft_challenge",
    "reason": "floor.soft.promo_stack"
  },
  {
    "id": "code_leak",
    "typology": "code_leak",
    "min_confidence": 0.7,
    "feature": null,
    "min_feature": null,
    "min_friction": "soft_challenge",
    "reason": "floor.soft.code_leak"
  }
]
```

Loader must:
- Point `_CAL_PATH` at `friction_v2_1.json`
- Require `interactions` list (each with id/a/b/alpha) and `soft_floors` list
- Keep weights sum check; reject `blend != weighted_sum`

- [ ] Failing test: missing `interactions` raises
- [ ] Implement; pytest green (expect version string updates across suite)
- [ ] Commit `feat: friction_v2_1 calibration skeleton`

**Note:** Temporarily score.py may still ignore interactions/floors until Tasks 2–3 — if full suite breaks only on version strings, fix those in this task.

---

### Task 2: Interaction blend + points contract

**Files:** `interactions.py`, `score.py`, `tests/test_interactions.py`, `tests/test_score_contract.py`

```python
# interactions.py
def interaction_results(
    confidences: dict[str, float], interactions: list[dict]
) -> list[TypologyResult]:
    """Return ix.* TypologyResult rows with points=round(100*alpha*c_a*c_b)."""

def blend_raw(weights, confidences, interactions) -> float:
    """Σ w c + Σ α c_a c_b, not clipped."""
```

`score.py`:

```python
conf = {r.id: r.confidence for r in results}
ix_rows = interaction_results(conf, cal.get("interactions") or [])
raw = blend_raw(weights, conf, cal.get("interactions") or [])
score = int(round(100.0 * clip(raw)))
breakdown = [r for r in results if r.confidence > 0] + [r for r in ix_rows if r.points > 0]
# reasons from typologies only (ix reasons optional: ["ix.multi_promo"] if points>0)
```

- [ ] Unit test: c_multi=1, c_promo=1, others 0 → raw = 0.28 + 0.18 + 0.22 = 0.68 → score 68
- [ ] Contract test: sum(points) ≈ score ±1 including ix
- [ ] Commit `feat: published interaction terms in score blend`

---

### Task 3: Soft floors

**Files:** `floors.py`, wire `score.py`, `tests/test_floors.py`

```python
FRICTION_ORDER = ["allow", "throttle", "soft_challenge", "hard_challenge", "block"]

def apply_soft_floors(
    band: FrictionAction,
    *,
    snapshot: dict,
    confidences: dict[str, float],
    soft_floors: list[dict],
) -> tuple[FrictionAction, list[str]]:
    """Raise friction only; return (friction, reason codes fired)."""
```

`evaluate()`:

```python
band = policy.action_for(score, force_hard_floor=False)
# hard floor still via force_hard_floor flag:
friction = policy.action_for(score, force_hard_floor=bool(snap.get("force_hard_floor")))
# then soft floors can raise further from `friction` (or apply soft then hard — order: band → soft → hard max)
friction, floor_reasons = apply_soft_floors(...)
friction = max_friction(friction, hard_floor_action)
reasons.extend(floor_reasons)
```

**Order (explicit):** start from score band → apply soft floors → enforce hard floor minimum (`hard_challenge` if `force_hard_floor`).

- [ ] Test: score would be allow, but multi c=0.8 and accounts_on_device_7d=5 → soft_challenge + `floor.soft.slow_multi`; score unchanged
- [ ] Test: soft floor never lowers hard_challenge
- [ ] Commit `feat: soft friction floors for pattern catch`

---

### Task 4: Adversarial + README claim update (Part A close)

**Files:** `eval/adversarial.py`, generators if needed, README, goldens

- Ensure pattern slices catch via ix and/or soft floor without velocity hard_floor vanity.
- Anti-vanity: still forbid redeem_5m padding; allow `floor.soft.*` as valid catch attribution.
- Update module docstring / README: soft catch may be floor-driven; lone typology score may stay < soft.
- Household ≥ 0.85; full pytest + adversarial seed 42 green.
- One α / floor knee retune allowed; document in report.

- [ ] Commit `test: adversarial gates under friction_v2_1 catch-power`
- [ ] Part A done — do not start Part B until this is green

---

## Part B — Shadow / label loop

### Task 5: Label join script

**Files:** `scripts/build_label_set.py`, `tests/test_label_set.py`, fixture JSON under `tests/fixtures/labels/`

```python
def build_label_rows(
    decisions: list[dict],
    outcomes: list[dict],
    clawbacks: list[dict] | None = None,
) -> list[dict]:
    """Join; provenance priority: clawback > challenge_failed > challenge_abandoned > ..."""
```

CLI: `--decisions`, `--outcomes`, `--clawbacks` optional, `--out`

- [ ] Test unknown decision_id dropped; failed challenge → label_abuse true
- [ ] Commit `feat: build_label_set join script`

---

### Task 6: Retrain calibration ECE gate

**Files:** `scripts/retrain_calibration.py`, `tests/test_retrain_calibration.py`

Reuse `loyalty_abuse.calibrate` fit/predict/ece. Write candidate params only if held-out ECE ≤ 0.05 or `--force`.

- [ ] Test: bad ECE does not overwrite file; good ECE writes; `--force` writes with note
- [ ] Commit `feat: ECE-gated calibration retrain script`

---

### Task 7: Four-week playbook + sim

**Files:**
- `docs/superpowers/playbooks/2026-08-05-shadow-four-week.md`
- `scripts/shadow_four_week_sim.py`
- `tests/test_shadow_four_week_sim.py` (smoke)

Playbook: weeks 1–4 checklist (shadow on → host logging → outcomes → weekly metrics → retrain candidate → promote).

Sim: generate ~28 days of synth events/decisions/outcomes; emit `artifacts/shadow_four_week_sim.json` with precision/recall/insult_proxy; banner note “not production A+”.

- [ ] Commit `feat: four-week shadow playbook and sim`

---

### Task 8: Ops floor attribution + Phase 4 closeout

**Files:** `analytics.py`, API tests, README, program spec status

- Add `floor_raised_rate` / counts: decisions where reasons contain `floor.soft.` or hard floor raised above pure score band (store `band_friction` in snapshot optional — or recompute band from score in analytics).
- Prefer: `evaluate` adds `features_snapshot["band_friction"]` = band before floors (tiny, honest attribution).
- README Phase 4 section: catch-power + shadow path; production A+/A++ still needs live 4 weeks.
- Program spec status line update.
- Full pytest + adversarial + drift_reeval green.

- [ ] Commit `chore: Phase 4 closeout`
- [ ] Stop

---

## Spec coverage

| Spec item | Task |
|---|---|
| Interaction terms + ix breakdown | 2 |
| Soft floors | 3 |
| friction_v2_1 cal | 1 |
| Adversarial / anti-vanity / household | 4 |
| Label join | 5 |
| Retrain ECE gate | 6 |
| Playbook + 28d sim | 7 |
| Ops floor attribution | 8 |
| No max_w / no false A++ claim | 4, 8 |

## Self-review notes

- Soft floor vs hard floor order is band → soft → hard.
- Interaction α values are starting points; Task 4 may retune once.
- Part B must not start before Task 4 green.
- `band_friction` in snapshot is the simplest attribution hook for Task 8.
