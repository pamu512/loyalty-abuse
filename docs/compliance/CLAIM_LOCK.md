# Claim lock — loyalty-abuse standalone

**Date:** 2026-08-06  
**Policy:** `friction_v3_0`  
**Program:** Twin-track v2 — `docs/superpowers/specs/2026-08-06-loyalty-abuse-v2-design.md`

## What may be claimed

| Claim | Status | Evidence |
|---|---|---|
| **B+** | MET | `artifacts/adversarial_v3_0.json` gates_pass |
| **Standalone A / A+ (technical)** | MET | Adversarial + external holdout + ablation + auth/deploy/dashboard + `/v1/decide` |
| **A++ path (in-repo)** | MET | Incognia fixture+live-gated; outcomes; drift; ops dashboard |
| **Production A+** | **NOT MET** | Needs ≥28d **live** shadow + ≥50 real outcome/clawback labels + ECE≤0.05; gate: `scripts/assert_production_a_plus.py` |
| **Production A++** | **NOT MET** | Live Incognia credentials required (`incognia-live.status` = BLOCKED) |

## Honesty notes (do not blur)

1. **Technical A+ ≠ Production A+.** In-repo proof is MET. Live ops proof is not.
2. **Synth calibration ECE** on score-path holdout is ~0.14 (target ceiling **0.15** for near-separable synth). Production outcome calibration must hit **ECE ≤ 0.05** via `fit_calibration_from_labels.py`.
3. **`shadow_four_week_sim*` is wiring only** — citing it as production A+ is forbidden.
4. **Cannot forge** `production-a-plus.evidence.json` with synth/red_team provenance — `assert_production_a_plus.py` exits 1.
5. **`LOYALTY_ABUSE_AUTH_DISABLED`** is test-only.

## Unlock production A+ (ops)

Follow `docs/superpowers/playbooks/2026-08-05-shadow-four-week.md`, then:

```bash
# after live weeks + real labels + ECE≤0.05 artifact:
# write docs/compliance/production-a-plus.evidence.json
python3 scripts/assert_production_a_plus.py   # must pass with MET only if evidence valid
```

Until then, `docs/compliance/production-a-plus.status` first line remains `NOT MET`.

## v2 surfaces (technical)

- Auth / tenant / rate limit / export; health/metrics/k8s/runbook; ops dashboard
- `friction_v3_0` typologies + graph depth + temporal Platt fit
- Unified `POST /v1/decide` (economics never denies orders)
