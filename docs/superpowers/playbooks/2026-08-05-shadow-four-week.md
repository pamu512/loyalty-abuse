# Four-Week Shadow Playbook

**Policy:** `friction_v2_1`  
**Purpose:** Ops checklist to reach an honest production A+ / A++ claim via live shadow — **not** via in-repo simulation.

> **Honesty banner:** The repo’s `scripts/shadow_four_week_sim.py` and `artifacts/shadow_four_week_sim.json` prove pipeline wiring only. They do **not** satisfy the live ≥4-week shadow requirement. Do not cite the sim as production A+ proof.

---

## Prerequisites

- [ ] `friction_v2_1` deployed; adversarial suite green in CI
- [ ] Shadow endpoint enabled: `POST /v1/shadow/evaluate` (recommended vs host)
- [ ] Host integration logs `host_friction` on every shadow call
- [ ] Challenge outcome ingestion path live (`passed` / `failed` / `abandoned`)
- [ ] Optional clawback/ban CSV feed keyed by `decision_id` or `event_id`
- [ ] Label join script: `scripts/build_label_set.py`
- [ ] Retrain script: `scripts/retrain_calibration.py` (ECE gate ≤ 0.05)

---

## Week 1 — Shadow on + host logging

**Goal:** Shadow scoring runs in production; host actions are logged; no enforcement change.

- [ ] Enable shadow evaluate for target tenant(s); live `/v1/evaluate` unchanged
- [ ] Confirm every shadow request includes `host_friction` (or document why absent)
- [ ] Verify `shadow_logs` rows: `decision_id`, `event_id`, `recommended_friction`, `host_friction`
- [ ] Daily volume check: events scored ≈ expected traffic
- [ ] Alert on shadow evaluate error rate
- [ ] **Do not** change host enforcement based on shadow recommendations yet
- [ ] Export weekly snapshot: shadow logs + decisions (if mirrored)

**Exit criteria:** ≥7 days of shadow logs with host friction populated; zero silent drops.

---

## Week 2 — Outcomes ingestion + label join

**Goal:** Later-confirmed labels flow into the label set without rescoring history.

- [ ] Ingest challenge outcomes within SLA (e.g. 72h after challenge)
- [ ] Run label join:
  ```bash
  PYTHONPATH=src:scripts python3 scripts/build_label_set.py \
    --decisions artifacts/decisions_w2.json \
    --outcomes artifacts/outcomes_w2.json \
    --out artifacts/label_set_w2.json
  ```
- [ ] Verify provenance priority: clawback > challenge_failed > challenge_abandoned > red_team > synth
- [ ] Confirm **no** historical decision scores were rewritten when labels arrived
- [ ] Track dropped rows (unknown `decision_id`) — investigate upstream gaps
- [ ] Weekly metrics (proxy until labels mature):
  - Precision / recall at soft_challenge+ (abuse vs clean from confirmed labels)
  - Insult proxy: clean accounts frictioned ≥ throttle

**Exit criteria:** Label set growing; provenance auditable; join script reproducible from exports.

---

## Week 3 — Weekly insult / $ + drift watch

**Goal:** Ops visibility before any calibration promotion.

- [ ] Pull ops analytics: insult rate, allow rate, expected $ vs allow-all
- [ ] Compare shadow `recommended_friction` vs `host_friction` divergence rate
- [ ] Floor attribution: count decisions where `floor.soft.*` or hard floor raised friction above score band
- [ ] Review false-positive clusters (clean + soft_challenge+ with passed outcomes)
- [ ] Review false-negative clusters (abuse + allow/throttle with later clawback)
- [ ] Document any policy tuning needs (α / floor knees) — one retune max, document in changelog
- [ ] Re-run label join with cumulative decisions + outcomes

**Exit criteria:** Weekly report published; no surprise insult spikes; floor catches labeled in reasons.

---

## Week 4 — Retrain candidate + promote (if ECE green)

**Goal:** Candidate calibration from locked train window; promote only on held-out ECE ≤ 0.05.

- [ ] Ensure ≥4 weeks of shadow data in label set (this week completes the live window)
- [ ] Split chronologically: train window locked; report window held out (never used for fit)
- [ ] Run retrain (dry-run first):
  ```bash
  PYTHONPATH=src:scripts python3 scripts/retrain_calibration.py \
    --labels artifacts/label_set_w4.json \
    --artifact-out artifacts/retrain_calibration_w4.json
  ```
- [ ] If held-out ECE > 0.05: **do not promote**; investigate calibration drift or label quality
- [ ] If ECE ≤ 0.05: review candidate params; promote via normal release process
- [ ] Post-promote: adversarial + pytest green on new calibration artifact
- [ ] Update README / claim language only after live 4-week evidence is documented externally

**Exit criteria:** Retrain artifact on disk; promotion decision recorded; production A+ claim supported by **live** shadow + labels, not sim.

---

## Sim reference (dev only)

Local pipeline check (not production proof):

```bash
PYTHONPATH=src:scripts python3 scripts/shadow_four_week_sim.py
# → artifacts/shadow_four_week_sim.json
```

The sim emits `precision`, `recall`, `insult_proxy`, weekly rollups, and a retrain-candidate preview using synthetic provenance. Treat it as wiring validation only.

---

## Claim checklist (production A+)

All must be true before claiming production A+:

- [ ] Live shadow ≥ **4 calendar weeks**
- [ ] Real later-confirmed outcome labels (not generator / synth provenance)
- [ ] Documented precision / recall / insult on held-out live labels
- [ ] Retrain held-out ECE ≤ 0.05 if calibration was updated during the window
- [ ] README and external comms cite live evidence — **not** `shadow_four_week_sim.json`
