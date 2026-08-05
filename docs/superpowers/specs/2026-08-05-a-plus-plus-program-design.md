# A++ Program Design — QSR Loyalty Abuse Engine

**Date:** 2026-08-05  
**Status:** Phase 3 path complete (Incognia adapter, challenge outcomes, ops loop); production A++ not claimed  
**Repo:** standalone `loyalty-abuse`  
**Prior art:** v1 engine + scoring math v1.1; critical review B−; path-to-A+ research canvas

## Goal

Move from an explainable rules engine with circular synth proof (B−) to an honest **A / A+** standalone bar, with a concrete **A++ trajectory** via Incognia device intelligence, challenge outcome feedback, and ops economics — without inventing a review queue or coupling core to any host.

## Locked decisions

| Decision | Choice |
|---|---|
| Program scope | Full three-phase roadmap; implement Phase 1 first |
| Device / attestation vendor | **Incognia** |
| Incognia credentials this cycle | Public API surface + VCR/fixtures; live calls gated on env |
| Architecture | Approach 1 — program spec + sequenced plans; core host-agnostic |
| Friction model | Keep `allow` → `throttle` → `soft_challenge` → `hard_challenge` → `block` (no `review`) |
| Observe contract | Only `evaluate()` calls `store.observe` for the scored event |

## Grade definitions (honest)

- **B+:** Non-circular adversarial eval can fail; score/points contract is true; soft-OR + multi-window reduce trivial evasion/FP blind spots.
- **A / A+ (standalone):** Dollar-weighted decisions, graph features with ablation, probability calibration (ECE/Brier), shadow reporter; production A+ additionally needs real outcome labels and ≥4 weeks shadow.
- **A++:** Operating system — strong device intel (Incognia), closed-loop challenge outcomes, continual drift re-eval, ops insult/loss dashboards; consortium hash exchange optional/additive.

Claiming a grade requires the artifact table under Testing and grade claims — not synth gate polish.

## Architecture

```
Mobile SDK (Incognia) → request_token on EventEnvelope.payload
        ↓
Host / API → optional adapters/incognia → IncogniaSignals into payload/features
        ↓
FeatureStore.snapshot (multi-window + later graph)
        ↓
Typology scorers (soft-OR) → weighted blend → Decision (score, friction, reasons)
        ↓
Host enforces friction → outcome webhook → labels → calibrate / cost re-tune (P2+)
```

**Boundaries**

- `loyalty_abuse` core: features, typologies, score, policy, calibration math — **never** imports FastAPI, Incognia, or Tarka.
- `loyalty_abuse_api`: HTTP, SQLite priors, analytics, shadow logging.
- `adapters/incognia/`: vendor client, signal normalization, fixture/live modes.
- `adapters/tarka/`: optional host mapper (unchanged role).
- Challenge enforcement: host-owned; core emits friction + reasons only.

## Phase 1 — Honest B+ (implement next)

`policy_version`: `friction_v1_2`

### Evaluation

- Primary proof: `scripts/adversarial_eval.py` (+ fixtures) with slices:
  - household false positives (shared device, legit multi-user)
  - device rotation (attacker avoids stable `device_id`)
  - slow multi-account (below 24h burst)
  - sequential promo stack (not simultaneous)
  - ATO on known device (no bare `new_device` / `new_geo` gift)
- Acceptance bounds per slice are published with the suite; **CI fails** if any slice misses.
- Existing 500k synth eval becomes **regression-only**; it must not be the grade claim.

### Score contract

- Remove silent `max_weight_normalize` as the meaning of score.
- With calibration weights summing to 1:  
  `score = round(100 * clip(Σ_i w_i * c_i))`
- `TypologyResult.points = round(100 * w_i * c_i)` for that typology.
- Invariant: `sum(points) ≈ score` within ±1 (rounding). Documented and tested.
- Economic fields (`expected_loss_usd`, etc.) are **Phase 2** — Phase 1 only fixes the points≡score contract.

### Typology math

- Replace intra-typology `max()` aggregation with soft-OR over evidence channels:  
  `c = 1 - Π_k (1 - c_k)` with each `c_k ∈ [0, 1]`.
- Add multi-window counters in `FeatureStore.snapshot`: `*_1h`, `*_24h`, `*_7d` for account / device / email / promo-code style rates. Scorers pick windows that match attack tempo (burst vs slow-roll).

### Out of Phase 1

Graph store, dollar thresholds, ECE calibration, Incognia client (event field hooks only if needed for forward compat).

## Phase 2 — Honest A / A+

### Economics

- Payload (nullable) monetary fields: `points_liability_usd`, `discount_usd`, `referral_bonus_usd`. Missing → 0 for $ objective; behavioral scoring still runs.
- Decision gains `expected_loss_usd` (and optionally `expected_insult_usd`) under a published cost model (`C_fn`, `C_fp` per friction rung).
- Friction band knees selected on a **locked validation** slice to minimize total expected cost; reported on held-out chronological / adversarial test. Never retune knees on the report set.

### Graph features (not GNN-first)

- Tenant edges: account–device–phone–payment_instrument_hash–email_domain–promo_code.
- Snapshot features: cluster size, age diversity, shared-attr rarity, multi-hop account count.
- Storage: SQLite-friendly adjacency sufficient; no new graph DB product required.
- Ablation artifact required: counters-only vs counters+graph on the same holdout.

### Calibration

- Treat `score/100` as abuse probability; fit Platt or isotonic on red-team and/or outcome labels.
- Publish ECE, Brier, reliability curve; target **ECE ≤ 0.05** on test.
- Document label provenance (red-team vs production outcomes).

### Shadow

- Shadow path: compute score + recommended friction; host action unchanged; log both.
- Production A+ claim: ≥4 weeks shadow with later-confirmed labels.
- This repo cycle: ship reporter + synthetic chronological shadow dry-run so the pipeline exists.

## Phase 3 — A++ trajectory (Incognia + ops loop)

### Incognia adapter

Path: `adapters/incognia/`  
Optional dependency: `incognia-python`

- Mobile/Web SDK supplies `request_token` (and optional `external_id`) on login, signup, and redeem-adjacent events via `EventEnvelope.payload`.
- Adapter calls vendor assessments (`register_login`, `register_new_signup`, payment-style as applicable) with `policy_id` from env.
- Maps raw assessment → normalized `IncogniaSignals` (risk level, tamper / device integrity, location trust, installation persistence hints). Exact field mapping pinned to fixture JSON derived from public SDK docs; updated when live sandbox responses are available.
- Core consumes only normalized signals (payload keys or a thin `DeviceIntel` protocol). **No** `import incognia` inside `loyalty_abuse`.
- Env for live mode: `INCOGNIA_CLIENT_ID`, `INCOGNIA_CLIENT_SECRET`, `INCOGNIA_POLICY_ID`. Absent → fixture / replay mode.
- Tenant config: if `incognia_required=true` and the call errors/times out → **fail-closed** for redeem (at least elevate friction / block per policy). If `incognia_required=false` → score without intel and emit reason `intel.incognia_unavailable`.

### Friction enforcement and labels

- Host executes `soft_challenge` / `hard_challenge`.
- Outcomes (`passed` / `failed` / `abandoned`) POST back within days as label events joined by `decision_id` / `event_id`.
- Incognia high risk may raise a friction floor (e.g. at least `hard_challenge`) without adding `review`.

### Consortium (optional, additive)

- Interface for hashed device / email / pay badness exchange.
- Default implementation: no-op / local-only until a partner exists.
- Incognia covers strong device identity; consortium is cross-merchant additive signal.

### Continual learning and ops

- Scheduled promo-adversarial re-eval; drift report when slice recall drops below bound.
- Ops metrics: insult rate, $ savings vs allow-all, Incognia success/latency, challenge conversion.

## Error handling

- Observe-only-in-`evaluate()` for the scored event remains invariant.
- Incognia timeout/5xx: fail-closed if required; else degrade with `intel.incognia_unavailable`.
- Late/missing challenge outcomes: do not silently rewrite historical scores; join labels when present for calibration / reporting.

## Testing and grade claims

| Claim | Required artifact |
|---|---|
| B+ | Adversarial suite green + points≡score contract tests + soft-OR / multi-window unit tests |
| A / A+ | $ objective report + graph ablation + ECE/Brier + shadow reporter (prod weeks for live A+) |
| A++ path | Incognia adapter (fixture + live-gated) + challenge outcome loop + ops metrics |

## Non-goals

- No `review` queue action.
- No GNN in core until graph features + labels prove need.
- No Tarka (or Incognia) imports in core.
- No A++ claim from synthetic cooperation alone.
- Consortium partner not required to complete the Incognia path.

## Deliverable sequencing

1. **This spec** (program).
2. **Implementation plan Phase 1** → implement → green adversarial suite + contract tests.
3. **Implementation plan Phase 2** → economics, graph features, calibration, shadow reporter.
4. **Implementation plan Phase 3** → Incognia adapter, challenge outcomes, ops metrics, optional consortium stub.

## Success criteria (program)

- Phase 1 merges only when adversarial suite and score contract tests pass.
- Phase 2 merges only when ablation + cost-threshold selection + calibration metrics are published as artifacts under `artifacts/` (gitignored raw) with a committed summary path or notebook.
- Phase 3 merges only when Incognia fixture tests pass and live mode is documented; challenge outcome ingest exists end-to-end in API or adapter tests.
- README states honest grade language tied to artifacts, not marketing.

