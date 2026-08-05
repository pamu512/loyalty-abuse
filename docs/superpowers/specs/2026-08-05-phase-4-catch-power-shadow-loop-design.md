# Phase 4 Design — Catch-Power + Shadow/Label Loop

**Date:** 2026-08-05  
**Status:** Implemented (catch-power + shadow/label loop + ops floor attribution); production A+/A++ not claimed  
**Branch base:** `feat/phase-3-a-plus-plus` (Phases 1–3 complete)  
**Program:** Extends `docs/superpowers/specs/2026-08-05-a-plus-plus-program-design.md`

## Goal

Raise honest soft-challenge reach for strong single-pattern abuse (without returning to `max_weight_normalize` theater), then close the production path for A+/A++ claims via a shadow → outcome → recalibration loop and a 4-week ops playbook.

## Locked decisions

| Decision | Choice |
|---|---|
| Scope | **B+D**: production shadow/label loop **and** catch-power redesign |
| Sequence | **A**: catch-power first, then shadow/label loop |
| Catch-power math | **Approach 1**: published interaction terms on the score |
| Catch-power friction | **Approach 3**: soft-floor predicates elevate friction only (score unchanged) |
| Policy version | `friction_v2_1` |
| Incognia / Phase 3 | Unchanged |

## Grade honesty

- Catch-power success does **not** by itself justify production A+ / A++.
- Production A+ / A++ still requires live shadow (≥4 weeks) and real outcome labels.
- The repo ships a **28-day synthetic shadow simulation** and a playbook; the sim must not be cited as production proof.

## Part A — Catch-power (`friction_v2_1`)

### Score: interaction terms

```
raw = Σ_i w_i · c_i + Σ_{(i,j)} α_{ij} · c_i · c_j
score = round(100 · clip(raw))
```

- Calibration weights still sum to `1.0 ± 1e-6`.
- Interaction coefficients `α_{ij}` are published in calibration JSON (not silent).
- Initial pair set (may retune once against adversarial, document if changed):
  - `multi_account × promo_stack`
  - `multi_account × code_leak`
  - `bot_redeem × multi_account`
  - `promo_stack × code_leak`
- Typology breakdown keeps `points_i = round(100 · w_i · c_i)`.
- Interaction contributions appear as explicit breakdown rows, e.g. `id: "ix.multi_promo"`, `points = round(100 · α · c_i · c_j)`, `confidence` unused or set to `c_i·c_j`.
- Contract: `sum(typology points + interaction points) ≈ score` within ±1.
- **Forbidden:** restoring `max_weight_normalize` / silent rescale.

### Friction: soft floors

After band mapping from score, apply soft-floor predicates that can only **raise** friction:

| Predicate | Min friction | Reason code |
|---|---|---|
| `multi_account` confidence ≥ 0.7 and `accounts_on_device_7d` ≥ 4 | `soft_challenge` | `floor.soft.slow_multi` |
| `promo_stack` confidence ≥ 0.6 and `stack_depth` ≥ 4 | `soft_challenge` | `floor.soft.promo_stack` |
| `code_leak` confidence ≥ 0.7 | `soft_challenge` | `floor.soft.code_leak` |
| Existing `force_hard_floor` / device intel floors | `hard_challenge` (unchanged) | existing reasons |

Rules:

- Soft floor = `max(band_action, min_friction)` — never lowers friction.
- Score, `p_abuse`, and economics continue to use the numeric score only (floors do not invent points).
- Floor reasons are appended to `Decision.reasons` (no new schema field required).
- Hard floors (velocity / ATO / Incognia) remain as today.

### Policy / evaluate wiring

```
results = typology scorers
score = blend(weights, confidences, interactions)
band = policy.action_for(score)  # without floors
friction = apply_floors(band, snapshot, results)  # soft + hard
```

`FrictionPolicy.action_for` may gain an optional post-pass or floors live in `evaluate()` after `action_for` — prefer keep `action_for` pure and apply floors in `evaluate()` / a small `floors.py` helper.

### Eval gates (Part A)

- Adversarial suite remains CI-gating; anti-vanity (no velocity hard_floor spam) stays.
- Pattern-oriented slices must be able to reach `soft_challenge+` via **interaction score and/or soft floor**, not redeem-velocity hard_floor padding.
- Soft-floor catches must include the matching `floor.soft.*` reason family (or typology family if score alone reaches soft).
- Household `allow_rate ≥ 0.85` preserved.
- Update honest B+ claim language: lone typology may still score below soft; soft catch may be floor-driven and must be labeled as such in README.

## Part B — Shadow / label loop

Depends on Part A landing (`friction_v2_1` stable).

### Label join

`scripts/build_label_set.py` joins:

- stored decisions (score, `p_abuse`, friction, reasons, ts)
- challenge outcomes (`passed` / `failed` / `abandoned`)
- optional host clawback / ban CSV (`decision_id` or `event_id` + label)

Output rows:

```
{decision_id, event_id, score, p_abuse, friction, label_abuse, provenance, ts}
```

Provenance enum: `challenge_failed` | `challenge_abandoned` | `clawback` | `red_team` | `synth`.

Do **not** rewrite historical decision scores when labels arrive.

### Retrain gate

`scripts/retrain_calibration.py`:

- Fit Platt (or existing calibrator) on a **locked train window**.
- Report ECE / Brier on a **held-out chronological** window.
- Refuse to overwrite published calibration params if held-out ECE > 0.05 unless `--force` (must log force in artifact).
- Never fit on the report window.

### Four-week playbook + sim

- Playbook: `docs/superpowers/playbooks/2026-08-05-shadow-four-week.md`  
  Week-by-week: enable shadow → log host action → ingest outcomes → weekly insult/$ → candidate retrain → promote.
- Sim: `scripts/shadow_four_week_sim.py` — synthetic ~28-day chronological dry-run producing an artifact report.
- Live ≥4 weeks remains an **ops** requirement for production A+ / A++ claims.

### Ops metrics

Extend analytics ops summary with:

- Insult rate: challenge+ (or hard+) on later-clean labels when available; else documented proxy
- $ savings vs allow-all (existing economics)
- Approval / allow rate
- Floor-vs-score attribution: count of decisions where soft/hard floor raised friction above the score band

## Architecture

```
Event → features → typologies (c_i)
      → score = 100·clip(Σ w c + Σ α c_i c_j)
      → band friction from score
      → soft/hard floors elevate friction only
      → Decision (score, p_abuse, economics, reasons)
Host shadow → outcomes / clawbacks → label set
      → retrain Platt (held-out ECE gate)
      → ops insult / $ / floor attribution
```

**Boundaries**

- Core remains free of FastAPI / Incognia / Tarka imports.
- Observe-only-in-`evaluate()` for the scored event unchanged.
- No `review` friction action.

## Error handling

- Missing interaction coeffs → treat as 0 (fail closed on cal load if required keys absent — prefer require keys listed in JSON).
- Soft-floor predicate errors → skip that floor, do not crash evaluate.
- Label join with unknown `decision_id` → drop or quarantine row; never mutate decisions.
- Retrain ECE fail → keep previous calibrator; exit non-zero unless `--force`.

## Testing

| Area | Evidence |
|---|---|
| Interaction math | Unit tests: known c vector → expected score/points including ix rows |
| Soft floors | Unit: low score + strong multi → soft_challenge + `floor.soft.slow_multi`; score unchanged |
| Contract | `sum(points) ≈ score` ±1 with ix rows |
| Adversarial | Seed 42 green; anti-vanity; pattern catch without velocity hard_floor vanity |
| Household | allow_rate ≥ 0.85 |
| Label join | Fixture CSV/outcomes → rows with provenance |
| Retrain gate | Toy set with ECE>0.05 refuses write; good set writes |
| Four-week sim | Script exits 0 and writes artifact |
| Ops attribution | Floor-raised decisions counted |

## Non-goals

- No return of `max_weight_normalize`.
- No `review` queue.
- No Phase 3 Incognia redesign.
- No production A++ claim from the 28-day sim alone.
- No GNN.

## Deliverable sequencing

1. This design spec (committed).
2. Implementation plan Phase 4 Part A (catch-power) → implement → green adversarial.
3. Implementation plan Phase 4 Part B (shadow loop) → implement → playbook + sim + retrain gate.
4. README / program status update: catch-power + shadow path; production A+/A++ still ops-gated.

## Success criteria

- Part A merges only when interaction contract + soft-floor tests + adversarial (incl. anti-vanity) pass.
- Part B merges only when label join, retrain ECE gate, playbook, and four-week sim exist with documented provenance.
- README states clearly: sim/playbook ≠ completed production 4-week shadow.
