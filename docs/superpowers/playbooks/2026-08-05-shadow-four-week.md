# Four-Week Shadow Playbook

**Policy:** `friction_v3_0`  
**Purpose:** Ops checklist to reach an honest **production A+** claim via live shadow — **not** via in-repo simulation.

> **Honesty banner:** `scripts/shadow_four_week_sim.py` and `artifacts/shadow_four_week_sim*.json` prove pipeline wiring only. They do **not** satisfy the live ≥4-week shadow requirement. Do not cite the sim as production A+ proof. Claim unlock requires `docs/compliance/production-a-plus.evidence.json` validated by `scripts/assert_production_a_plus.py`.

---

## Prerequisites

- [ ] `friction_v3_0` deployed; `artifacts/adversarial_v3_0.json` gates_pass in CI
- [ ] Auth enabled in production (`LOYALTY_ABUSE_AUTH_DISABLED` **unset**)
- [ ] Shadow path: `POST /v1/shadow/evaluate` **or** `POST /v1/decide` with tenant `evaluation_mode=shadow`
- [ ] Host logs `host_friction` on every shadow call
- [ ] Challenge outcome ingestion live (`POST /v1/challenge_outcomes`)
- [ ] Optional clawback/ban feed keyed by `decision_id` / `event_id`
- [ ] Label join: `scripts/build_label_set.py`
- [ ] Outcome calibration: `scripts/fit_calibration_from_labels.py` (ECE ≤ 0.05; refuses synth-only)
- [ ] Production claim gate green when NOT MET: `python3 scripts/assert_production_a_plus.py`

---

## Week 1 — Shadow on + host logging

**Goal:** Shadow scoring runs on live traffic; host actions logged; no enforcement change.

- [ ] Set tenant mode `shadow` via `PUT /v1/admin/tenants/{id}/mode`
- [ ] Prefer `POST /v1/decide` (unified envelope) or `/v1/shadow/evaluate`
- [ ] Confirm every shadow request includes `host_friction` when using shadow evaluate
- [ ] Verify `shadow_logs` rows populate; export via `GET /v1/export/shadow`
- [ ] Daily volume ≈ expected traffic; alert on error rate
- [ ] **Do not** change host enforcement from shadow recommendations yet

**Exit criteria:** ≥7 days shadow logs with host friction populated; zero silent drops.

---

## Week 2 — Outcomes ingestion + label join

**Goal:** Later-confirmed labels flow without rescoring history.

- [ ] Challenge outcomes for soft/hard challenges (`passed` / `failed` / `abandoned`)
- [ ] Optional clawbacks/bans joined by `decision_id`
- [ ] Run `scripts/build_label_set.py` → `artifacts/label_set_live_w2.json`
- [ ] Provenance must be `challenge_*` / `clawback` — not `synth` / `red_team`
- [ ] Ops dashboard: insult proxy, floor attribution, challenge fail rate

**Exit criteria:** ≥50 labeled rows with production provenance; join script audited.

---

## Week 3 — Calibration + knees on live labels

**Goal:** Fit calibrator on live labels; ECE ≤ 0.05 on temporal holdout.

- [ ] `scripts/fit_calibration_from_labels.py --labels artifacts/label_set_live_*.json`
- [ ] Confirm exit 0 and `meets_ece_target` with ECE ≤ 0.05
- [ ] Optional: re-select cost knees on locked val (never on report set)
- [ ] Drift: `scripts/drift_reeval.py` still green on adversarial suite

**Exit criteria:** Platt artifact with production provenance; ECE ≤ 0.05.

---

## Week 4 — Review + claim packet

**Goal:** Assemble production A+ evidence or stay NOT MET honestly.

- [ ] Confirm ≥28 calendar days from `shadow_start` to `shadow_end`
- [ ] Fill `docs/compliance/production-a-plus.evidence.json` per schema
- [ ] Attestation: `not_simulation=true`, `live_traffic=true`, named operator
- [ ] Run `python3 scripts/assert_production_a_plus.py` — must pass before flipping status to MET
- [ ] Only then set `docs/compliance/production-a-plus.status` first line to `MET — …`
- [ ] Update `CLAIM_LOCK.md`

**If evidence fails:** leave status `NOT MET`. Do not forge.

---

## Production A++ (separate)

Requires Incognia live credentials + successful live assessment smoke. See `docs/compliance/incognia-live.status`. Fixture mode is not A++.
