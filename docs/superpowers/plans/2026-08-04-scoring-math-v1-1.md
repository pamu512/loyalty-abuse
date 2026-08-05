# Scoring Math v1.1 + Synth 500k Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (or subagent-driven-development) to implement task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship normalized confidence blend scoring (`friction_v1_1`), feature logic fixes, and a reproducible 500k synthetic eval with acceptance gates.

**Architecture:** Calibration JSON drives weights/sat knees/bands. Typology scorers return `confidence ∈ [0,1]`; `evaluate()` blends \(100\sum w_i c_i\). FeatureStore fixes scoped email burst, ATO `new_device`/`new_geo`, referral set intersection. `scripts/synth_eval.py` generates labeled journeys and reports metrics in-process.

**Tech Stack:** Python 3.12, existing pydantic/pytest stack, stdlib JSON

**Spec:** `docs/superpowers/specs/2026-08-04-scoring-math-v1-1-design.md` (uncommitted until user asks)

## Global Constraints

- Weights must sum to 1.0 ± 1e-6 at calibration load (fail closed).
- Friction bands stay 24/44/64/84; `policy_version` = `friction_v1_1`.
- Hard floor hybrid: ATO / extreme bot still set `force_hard_floor`; confidences still contribute to score.
- Observe only inside `evaluate()` for the scored event (API rebuild priors).
- No `review` action; no ML training.
- Synth eval: seed 42, n=500000, in-process, aggregates + optional sample; do not require HTTP.
- Do not commit the design spec unless user requests.

## File Structure

| Path | Role |
|---|---|
| `src/loyalty_abuse/calibration/friction_v1_1.json` | Weights, sat, bands, floor |
| `src/loyalty_abuse/calibration/__init__.py` | Load + validate |
| `src/loyalty_abuse/mathutil.py` | `sat()`, `clip()` |
| `src/loyalty_abuse/features.py` | Logic fixes |
| `src/loyalty_abuse/typologies/*.py` | Confidence scorers |
| `src/loyalty_abuse/score.py` | Weighted blend |
| `src/loyalty_abuse/schema.py` | `confidence` on TypologyResult; POLICY_VERSION |
| `contracts/decision.schema.json` | confidence field |
| `scripts/synth_eval.py` | Generator + metrics + compare |
| `tests/test_calibration.py`, `test_mathutil.py`, feature/evaluate updates | |

---

### Task 1: Calibration + sat()

**Files:** Create calibration JSON + loader + `mathutil.py`; tests.

- [ ] Test `sat(5, 0, 10) == 0.5`, clamp outside; test weights sum reject
- [ ] Implement loader + `sat`
- [ ] pytest pass (no commit required if user prefers batch commit at end)

### Task 2: Feature logic fixes

**Files:** `features.py`, `tests/test_features.py`

- [ ] Scoped email burst; ATO requires new_device or new_geo; referral set intersection
- [ ] Update/add tests; full features suite green

### Task 3: Confidence scorers + evaluate blend

**Files:** all typology modules, `score.py`, schema `confidence` + POLICY_VERSION

- [ ] Scorers return TypologyResult with confidence + contribution points
- [ ] evaluate: score = round(100 * clip(sum w*c)); floor unchanged
- [ ] Update goldens / evaluate tests for new distributions
- [ ] contracts decision schema + confidence

### Task 4: Synth 500k eval

**Files:** `scripts/synth_eval.py`, `artifacts/` gitignored

- [ ] Generator mixture per spec; `--n --seed --policy --out`
- [ ] Metrics + gates; `--compare` two JSON reports
- [ ] Run `--n 500000 --seed 42 --policy friction_v1_1`
- [ ] Document results in `artifacts/synth_500k_v1_1_summary.md` (uncommitted ok)
- [ ] If gates fail, retune calibration JSON once and re-run same seed

---

## Spec coverage

| Spec item | Task |
|---|---|
| Normalized blend | 3 |
| Calibration table | 1 |
| Feature fixes | 2 |
| Hybrid hard floor | 3 |
| Schema confidence | 3 |
| 500k synth + gates | 4 |
