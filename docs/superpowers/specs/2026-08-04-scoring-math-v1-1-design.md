# Scoring Math v1.1 — Design

**Date:** 2026-08-04  
**Status:** SUPERSEDED — historical only. Do **not** implement or re-enable.  
**Live policy:** `friction_v2_1` (`src/loyalty_abuse/calibration/friction_v2_1.json`).  
**Superseded by:** Phase 1 `friction_v1_2` (drop `max_weight_normalize` → `weighted_sum`, soft-OR, multi-window) then Phase 2–4 (`friction_v2_0` / `friction_v2_1`: economics, interactions, soft floors, adversarial claim).  
**Why archived:** `max_weight_normalize` lets a single typology hit score 100; `points` vs score diverge; synth-500k gates are circular. Kept for provenance, not as a ship target.  
**Originally superseded scoring behavior in:** `docs/superpowers/specs/2026-08-04-loyalty-abuse-design.md` (friction ladder + typologies unchanged in *intent*; math upgraded)  
**Policy version (this draft):** `friction_v1_1` (bands unchanged; weights/curves live in a calibration table)

## Goal

Replace flat binary typology points with **normalized confidence scores** blended by calibrated weights, fix feature logic bugs that inflate or mis-scope risk, and **validate** the new model on **~500k synthetic journeys** before treating v1.1 as shippable.

## Locked decisions

| Decision | Choice |
|---|---|
| Scope | Logic fixes **and** scoring upgrade |
| Hard floor vs points | **Hybrid:** modest/high confidence still contributes to score; `force_hard_floor` still forces friction ≥ `hard_challenge` |
| Friction bands | Keep 24 / 44 / 64 / 84 for v1.1; publish calibration table so bands can move later via `policy_version` only |
| Math approach | **Normalized sub-scores then blend** (not piecewise ladders, not raw log-only sum) |

## Non-goals

- ML training / GBM (still rules + formulas)
- Cross-merchant consortium
- Changing the friction action enum
- Analyst review disposition
- Committing this spec until explicitly requested

---

## 1. Scoring math

### 1.1 Per-typology confidence

Each typology scorer returns:

- `confidence` \(c_i \in [0, 1]\)
- `reasons[]` (non-empty iff \(c_i > 0\), or iff a named reason threshold fired — see below)
- `points` = contribution to master score for API compat: \(\mathrm{round}(100 \cdot w_i \cdot c_i)\)

### 1.2 Master score

\[
\text{raw} = \frac{\sum_i w_i\, c_i}{\max_j w_j},\quad
\text{score} = \mathrm{round}\big(100 \cdot \mathrm{clip}_{[0,1]}(\text{raw})\big)
\]

Weights must satisfy \(\sum_i w_i = 1\) (asserted at calibration load; tolerance \(10^{-6}\)).  
**Blend mode `max_weight_normalize`:** dividing by \(\max w_j\) lets a single typology at \(c=1\) reach score 100; without it, \(\sum w c \le \max w\) would cap a lone signal near ~22 and never hit throttle alone.

### 1.3 Default weights

| typology | \(w_i\) |
|---|---|
| `ato_redeem` | 0.22 |
| `multi_account` | 0.18 |
| `bot_redeem` | 0.18 |
| `referral_self_deal` | 0.14 |
| `code_leak` | 0.14 |
| `promo_stack` | 0.14 |

### 1.4 Saturating transform

\[
\mathrm{sat}(x; a, b) = \mathrm{clip}_{[0,1]}\Big(\frac{x - a}{b - a}\Big)
\quad (b > a)
\]

Used for count-like features. Binary sequence signals (ATO chain) map to a fixed high confidence when true.

### 1.5 Confidence definitions (v1.1 defaults)

Knees \((a,b)\) live in the calibration table; defaults:

| typology | confidence formula (sketch) |
|---|---|
| `multi_account` | \(c = \max\big(\mathrm{sat}(n_{\mathrm{dev}}; 2, 8),\; \mathrm{sat}(n_{\mathrm{ip}}; 3, 12),\; 0.75\cdot\mathbb{1}_{\mathrm{email\_burst\_scoped}}\big)\); if `account_age_minutes < 60` and \(n_{\mathrm{dev}}\ge 2\), \(c \leftarrow \min(1, c\cdot 1.1)\) |
| `referral_self_deal` | \(c = \max(0.9\cdot\mathbb{1}_{\mathrm{shared\_device}},\; 0.85\cdot\mathbb{1}_{\mathrm{shared\_payment}},\; 1.0\cdot\mathbb{1}_{\mathrm{both}})\) |
| `promo_stack` | \(c = \max\big(\mathrm{sat}(\mathrm{stack}; 2, 5),\; \mathrm{sat}(\mathrm{discount\_pct}; 30, 70)\big)\) |
| `bot_redeem` | \(c = \max\big(\mathrm{sat}(r_{5m}; 4, 18),\; \mathrm{sat}(s_{5m}; 3, 12)\big)\); if age &lt; 60m, \(c \leftarrow \min(1, c\cdot 1.15)\) |
| `code_leak` | \(c = \mathrm{sat}(u_{24h}; 15, 60)\) on active promo/referral code |
| `ato_redeem` | \(c = 0.85\) if `ato_chain` else \(0\) |

**Reasons:** emit a reason code when the corresponding signal contributes (e.g. device sat &gt; 0 → `multi_acct.shared_device_cluster`; scoped email burst → `multi_acct.email_alias_burst`). Avoid emitting reasons when \(c=0\).

### 1.6 Friction + hard floor (hybrid)

Bands unchanged:

| score | action |
|---|---|
| 0–24 | `allow` |
| 25–44 | `throttle` |
| 45–64 | `soft_challenge` |
| 65–84 | `hard_challenge` |
| 85–100 | `block` |

`force_hard_floor` still true when:

- `ato_chain`, or
- `redeem_count_5m >= 20`, or
- `signup_count_5m >= 15`

When true: friction = max(score-mapped action, `hard_challenge`) in ladder order. Typology confidences still contribute to `score` (no zeroing).

### 1.7 Calibration table

Path: `src/loyalty_abuse/calibration/friction_v1_1.json`

Contents:

- `policy_version`
- `weights`
- `bands` (`allow_max`, `throttle_max`, `soft_max`, `hard_max`)
- `sat` knees per signal
- `hard_floor` thresholds
- `young_account_minutes`, `young_bot_mult`, `young_multi_mult`
- `ato_confidence` (default 0.85)

Load once at import / process start; fail closed if weights do not sum to 1.

`POLICY_VERSION` constant and Decision default become `friction_v1_1`.

---

## 2. Feature / logic fixes

| Issue | Fix |
|---|---|
| `email_alias_burst` any tenant root ≥3 | **Scoped:** root of current account’s email has ≥3 distinct accounts in 24h (or current account is in a root with ≥3). Snapshot field: `email_alias_burst` means scoped (breaking rename acceptable in v1.1; update tests). |
| ATO login: `new_device` or truthy `geo` | Require `payload.new_device == true` **or** `payload.new_geo == true`. A geo string alone does not qualify. |
| Unused `account_age_minutes` | Used in multi_account / bot confidence multipliers (calibration). |
| Referral last-seen device overwrite | Shared device/payment if **any** historical device_id / payment hash intersects between referrer and referee sets. |
| Code users | Unchanged window logic; confidence uses sat instead of binary ≥25. |

Observe-only-inside-`evaluate()` decision **unchanged**.

---

## 3. Schema

`TypologyResult`:

- add `confidence: float` (0–1)
- keep `points` as contribution \(\mathrm{round}(100\cdot w\cdot c)\)
- `id`, `reasons` unchanged

Contracts JSON updated in lockstep. `schema_version` stays `1` unless we need a breaking bump for hosts; document `confidence` as additive field (forward compatible).

---

## 4. Synthetic evaluation — 500k journeys

### 4.1 Purpose

Before shipping v1.1 scoring:

1. **Baseline** current `friction_v1` (or freeze a replay of today’s scorers) on the same 500k.
2. **Candidate** `friction_v1_1` on the same 500k.
3. Compare friction mix, score distributions, typology hit rates, and **labeled-segment recall/precision proxies**.

### 4.2 Generator design

Script: `scripts/synth_eval.py` (or `notebooks/synth_500k_eval.py`)

Emit **500_000** labeled synthetic *decision subjects* (each subject = a short event sequence ending in an evaluate-worthy event: usually `redeem` / `checkout` / `referral` / `signup`).

**Mixture (defaults, adjustable via CLI):**

| Segment label | Share | Approx count | Construction |
|---|---|---|---|
| `clean` | 70% | 350k | Normal account age, single device, 0–1 offer, human-like gaps |
| `multi_account` | 6% | 30k | 3–12 accounts sharing device/IP; optional email `+` aliases |
| `referral_self_deal` | 4% | 20k | Referrer/referee share device and/or payment |
| `promo_stack` | 4% | 20k | stack_depth 3–6 and/or discount_pct 40–90 |
| `bot_redeem` | 5% | 25k | High redeem/signup velocity on device in 5m |
| `code_leak` | 4% | 20k | Same code across 20–80 unique users in 24h |
| `ato_redeem` | 4% | 20k | new_device login → profile_update → redeem within 30m |
| `mixed_hard` | 3% | 15k | Combine 2+ abuse patterns (stress blend + floor) |

Total 100%. Deterministic RNG seed (default `42`) for reproducibility.

Each subject produces:

- ordered `EventEnvelope[]` (prior events + terminal event)
- `label` (segment)
- optional `expected_min_friction` / `expected_reason_substrings` for strong segments (not for clean)

### 4.3 Metrics (offline report)

Write JSON + stdout summary:

- Friction histogram (v1 vs v1.1)
- Score histogram (10-point buckets)
- Per-typology: rate of \(c_i > 0\) (or points &gt; 0)
- Per labeled segment:
  - **Recall proxy:** share with friction ≥ segment threshold (e.g. abuse segments ≥ `throttle`; `ato`/`mixed_hard` ≥ `hard_challenge`)
  - **Precision proxy (weak):** among decisions with friction ≥ `soft_challenge`, share whose label ≠ `clean`
  - Clean **allow rate** (target: high; flag if &lt; 95% on clean without tuning note)
- Hard-floor trigger rate by segment
- Top reasons overall

**Acceptance gates (v1.1 candidate, tunable after first run):**

| Gate | Target |
|---|---|
| Clean → `allow` | ≥ 95% |
| `ato_redeem` → ≥ `hard_challenge` | ≥ 90% |
| `bot_redeem` → ≥ `throttle` | ≥ 85% |
| `multi_account` → ≥ `throttle` | ≥ 80% |
| Among `soft_challenge+`, label ≠ clean | ≥ 70% (precision proxy) |
| Weight sum / calibration load | 100% pass unit tests |

First 500k run may **fail** gates; then adjust calibration JSON (not ad-hoc scorer branches) and re-run with same seed.

### 4.4 Performance

Target: evaluate 500k subjects in-process (no HTTP) on a laptop in **&lt; 15 minutes**. Use batch FeatureStore per subject (fresh store each journey). Optional progress every 25k. Persist only aggregates + a sample of 1k scored rows for spot checks (not all 500k decisions unless `--full-out` path provided).

### 4.5 CLI sketch

```bash
python scripts/synth_eval.py --n 500000 --seed 42 --policy friction_v1_1 --out artifacts/synth_500k_v1_1.json
python scripts/synth_eval.py --n 500000 --seed 42 --policy friction_v1 --out artifacts/synth_500k_v1.json
python scripts/synth_eval.py --compare artifacts/synth_500k_v1.json artifacts/synth_500k_v1_1.json
```

---

## 5. Implementation shape (for later plan; not started)

1. Calibration loader + `sat()` helper + weight assert  
2. Feature logic fixes + tests  
3. Typology scorers → confidence model; `evaluate()` blend  
4. Schema/contracts `confidence` field  
5. Retune unit/golden tests  
6. `scripts/synth_eval.py` + 500k run + compare report  
7. Calibration iteration until gates pass or documented exceptions  

---

## 6. Success criteria

1. Spec approved; then implementation lands with `policy_version=friction_v1_1`.  
2. Unit/golden suite green.  
3. Reproducible 500k synth eval (seed 42) produced for v1.1.  
4. Acceptance gates met **or** explicit signed exceptions in the eval report.  
5. Clean traffic allow-rate and ATO hard-floor behavior documented in the eval artifact.

## Open points (resolve during first 500k run if needed)

- Exact clean allow-rate if generator is slightly “dirty” by construction — fix generator before loosening gates.  
- Whether `points` in breakdown should remain contribution-based when hosts already sum them (yes: document sum(points) ≈ score subject to rounding).  
- Optional second seed run for stability check (not required for v1.1).
