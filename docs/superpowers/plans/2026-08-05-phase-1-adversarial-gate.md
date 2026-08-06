# Phase 1 — Adversarial gate Implementation Plan

> **Privacy:** Letter-grade maturity ratings are private ([`docs/compliance/RATINGS_PRIVATE.md`](../../compliance/RATINGS_PRIVATE.md)). This document uses capability language only.


> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship `friction_v1_2`: honest score/points contract (no `max_weight_normalize`), soft-OR inside typologies, multi-window features, and an adversarial eval suite that is the primary adversarial suite proof.

**Architecture:** Calibration JSON switches to `blend: "weighted_sum"` with `policy_version: friction_v1_2`. `soft_or()` combines intra-typology evidence. `FeatureStore.snapshot` emits `*_1h` / `*_24h` / `*_7d` counters; scorers prefer the window matching attack tempo. `scripts/adversarial_eval.py` is CI-gating; 500k synth stays regression-only.

**Tech Stack:** Python 3.12, pydantic, pytest, existing `loyalty_abuse` library (no new deps)

**Spec:** `docs/superpowers/specs/2026-08-05-maturity-program-design.md` (Phase 1 section)

## Global Constraints

- Core must never import FastAPI, Incognia, or Tarka.
- Only `evaluate()` calls `store.observe` for the scored event.
- No `review` friction action.
- Weights must sum to 1.0 ± 1e-6 at calibration load.
- Friction bands stay 24/44/64/84 unless goldens prove a one-time retune is required (document if retuned).
- `policy_version` = `friction_v1_2`.
- `sum(typology.points) ≈ score` within ±1.
- Adversarial suite is the readiness claim; synth 500k is not.
- Uncommitted v1.1 work on `main` must be landed (Task 0) before v1.2 edits.

## File Structure

| Path | Role |
|---|---|
| `src/loyalty_abuse/calibration/friction_v1_1.json` | Keep as historical artifact OR delete after v1.2 lands — prefer keep + loader points at v1.2 only |
| `src/loyalty_abuse/calibration/friction_v1_2.json` | New calibration: `blend: weighted_sum`, multi-window sat keys |
| `src/loyalty_abuse/calibration/__init__.py` | Load `friction_v1_2.json`; validate blend |
| `src/loyalty_abuse/mathutil.py` | Add `soft_or(cs: list[float]) -> float` |
| `src/loyalty_abuse/features.py` | Multi-window counters |
| `src/loyalty_abuse/typologies/*.py` | soft-OR; consume multi-window keys |
| `src/loyalty_abuse/score.py` | Drop max_weight_normalize; assert points≈score |
| `src/loyalty_abuse/schema.py` | `POLICY_VERSION = "friction_v1_2"` |
| `contracts/decision.schema.json` | policy_version examples if any |
| `scripts/adversarial_eval.py` | Five slices + bounds + exit code |
| `tests/test_mathutil.py` | soft_or tests |
| `tests/test_score_contract.py` | points≡score |
| `tests/test_features.py` | multi-window |
| `tests/test_adversarial_eval.py` | thin wrapper / fixture slices |
| `tests/fixtures/golden_tiers.json` | Retune expected frictions for v1.2 |
| `README.md` | Note adversarial gate claim via adversarial suite |

---

### Task 0: Land uncommitted v1.1 baseline

**Files:** All currently modified/untracked v1.1 scoring files (calibration, typologies, synth_eval, tests). Do **not** commit `docs/superpowers/specs/2026-08-04-scoring-math-v1-1-design.md` unless user previously allowed (default: leave untracked).

**Interfaces:**
- Consumes: working tree v1.1 implementation
- Produces: clean `main` with `friction_v1_1` green tests as parent of v1.2 commits

- [ ] **Step 1: Run full test suite**

```bash
cd /Users/pamu/Documents/GitHub/loyalty-abuse && python -m pytest -q
```

Expected: all tests PASS (fix any failures before committing).

- [ ] **Step 2: Commit v1.1 code (not the forbidden design doc)**

```bash
git add \
  .gitignore \
  contracts/decision.schema.json \
  pyproject.toml \
  src/loyalty_abuse/calibration/ \
  src/loyalty_abuse/mathutil.py \
  src/loyalty_abuse/features.py \
  src/loyalty_abuse/schema.py \
  src/loyalty_abuse/score.py \
  src/loyalty_abuse/typologies/ \
  scripts/synth_eval.py \
  tests/fixtures/golden_tiers.json \
  tests/test_calibration.py \
  tests/test_mathutil.py \
  tests/test_features.py \
  tests/test_contracts.py \
  tests/test_schema.py \
  docs/superpowers/plans/2026-08-04-scoring-math-v1-1.md
git commit -m "$(cat <<'EOF'
feat: ship friction_v1_1 confidence blend and synth eval

EOF
)"
```

- [ ] **Step 3: Verify clean relevant tree**

```bash
git status -sb
```

Expected: v1.1 paths committed; design spec for v1.1 may remain untracked.

---

### Task 1: `soft_or` math helper

**Files:**
- Modify: `src/loyalty_abuse/mathutil.py`
- Modify: `tests/test_mathutil.py`

**Interfaces:**
- Consumes: existing `clip`
- Produces: `soft_or(confidences: list[float]) -> float` where empty → 0.0; each input clipped to [0,1]; result `1 - Π(1 - c_k)`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_mathutil.py`:

```python
from loyalty_abuse.mathutil import soft_or

def test_soft_or_empty():
    assert soft_or([]) == 0.0

def test_soft_or_single():
    assert soft_or([0.5]) == 0.5

def test_soft_or_independent():
    # 1 - (1-0.5)*(1-0.5) = 0.75
    assert abs(soft_or([0.5, 0.5]) - 0.75) < 1e-9

def test_soft_or_clips():
    assert soft_or([-1.0, 2.0]) == 1.0
```

- [ ] **Step 2: Run tests — expect FAIL**

```bash
python -m pytest tests/test_mathutil.py::test_soft_or_independent -v
```

Expected: FAIL import or attribute error for `soft_or`.

- [ ] **Step 3: Implement**

Append to `src/loyalty_abuse/mathutil.py`:

```python
def soft_or(confidences: list[float]) -> float:
    """Combine evidence channels: 1 - Π(1 - c_k), c clipped to [0, 1]."""
    if not confidences:
        return 0.0
    prod = 1.0
    for c in confidences:
        prod *= 1.0 - clip(float(c))
    return clip(1.0 - prod)
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
python -m pytest tests/test_mathutil.py -v
```

- [ ] **Step 5: Commit**

```bash
git add src/loyalty_abuse/mathutil.py tests/test_mathutil.py
git commit -m "feat: add soft_or evidence combiner"
```

---

### Task 2: Multi-window feature counters

**Files:**
- Modify: `src/loyalty_abuse/features.py`
- Modify: `tests/test_features.py`

**Interfaces:**
- Consumes: `FeatureStore._in_window`, EventEnvelope
- Produces: snapshot keys (in addition to existing 24h keys kept for back-compat during migration):
  - `accounts_on_device_1h`, `accounts_on_device_24h`, `accounts_on_device_7d`
  - `accounts_on_ip_1h`, `accounts_on_ip_24h`, `accounts_on_ip_7d`
  - `code_unique_users_1h`, `code_unique_users_24h`, `code_unique_users_7d`
  - `email_alias_burst_1h`, `email_alias_burst_24h`, `email_alias_burst_7d` (bool)
  - Keep `redeem_count_5m` / `signup_count_5m` unchanged (bot burst)
  - Keep legacy `email_alias_burst` == `email_alias_burst_24h` for one release

- [ ] **Step 1: Write failing test**

```python
from datetime import datetime, timedelta, timezone
from loyalty_abuse.features import FeatureStore
from loyalty_abuse.schema import EventEnvelope, EventType

def _ev(eid, acct, device, hours_ago, now):
    ts = (now - timedelta(hours=hours_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return EventEnvelope(
        event_id=eid, tenant_id="t", ts=ts, type=EventType.signup,
        account_id=acct, session_id=eid, device_id=device, ip="1.1.1.1", payload={},
    )

def test_device_accounts_multi_window():
    now = datetime(2026, 8, 5, 12, 0, tzinfo=timezone.utc)
    store = FeatureStore()
    store.observe(_ev("a", "a1", "d", 0.5, now))   # 30m ago → 1h+24h+7d
    store.observe(_ev("b", "a2", "d", 3, now))     # 3h → 24h+7d only
    store.observe(_ev("c", "a3", "d", 48, now))    # 2d → 7d only
    cur = EventEnvelope(
        event_id="r", tenant_id="t",
        ts=now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        type=EventType.redeem, account_id="a1", session_id="s",
        device_id="d", ip="1.1.1.1",
        payload={"reward_id": "r", "points": 1, "offer_ids": [], "channel": "app"},
    )
    store.observe(cur)
    snap = store.snapshot(cur)
    assert snap["accounts_on_device_1h"] == 1   # only a1 in 1h (current not double-counted if observe includes it — document: snapshot includes observed events ≤ now)
    assert snap["accounts_on_device_24h"] == 2
    assert snap["accounts_on_device_7d"] == 3
```

**Note for implementer:** If `evaluate()` observes before snapshot, the current redeem is on device `d` with account `a1` — so 1h count is still 1 account (`a1`), 24h is `{a1,a2}`, 7d `{a1,a2,a3}`. Adjust asserts to match set-cardinality of `account_id` (not event count).

- [ ] **Step 2: Run — expect FAIL**

```bash
python -m pytest tests/test_features.py::test_device_accounts_multi_window -v
```

- [ ] **Step 3: Implement multi-window in `snapshot`**

Refactor `features.py` to compute account sets for windows `1h`, `24h`, `7d`:

```python
windows = {
    "1h": timedelta(hours=1),
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
}
# for each label, window in windows:
#   on_device = _in_window(now, window, device pred)
#   snap[f"accounts_on_device_{label}"] = len({e.account_id for e in on_device})
# same for IP; same for code_unique_users; email roots per window
```

Keep existing keys `accounts_on_device_24h` etc. as the `24h` values (no duplicate logic paths).

- [ ] **Step 4: Run feature tests**

```bash
python -m pytest tests/test_features.py -v
```

Expected: PASS (update any tests that assumed only 24h keys if they break on extras — extras are fine).

- [ ] **Step 5: Commit**

```bash
git add src/loyalty_abuse/features.py tests/test_features.py
git commit -m "feat: multi-window device/ip/code/email counters"
```

---

### Task 3: Typologies use soft-OR + multi-window

**Files:**
- Modify: `src/loyalty_abuse/typologies/multi_account.py`
- Modify: `src/loyalty_abuse/typologies/promo_stack.py`
- Modify: `src/loyalty_abuse/typologies/bot_redeem.py`
- Modify: `src/loyalty_abuse/typologies/code_leak.py`
- Modify: `src/loyalty_abuse/typologies/referral_self_deal.py` (soft-OR device/payment channels)
- Create: `tests/test_soft_or_typologies.py`

**Interfaces:**
- Consumes: `soft_or`, `sat`, multi-window snapshot keys, `result()`
- Produces: typology confidences via soft-OR of channels (not `max`)

- [ ] **Step 1: Failing typology unit test**

```python
from loyalty_abuse.typologies import multi_account

def test_multi_account_soft_or_not_max():
    # device sat mid + email burst should exceed max(device, email) alone when both fire
    snap = {
        "accounts_on_device_1h": 0,
        "accounts_on_device_24h": 4,
        "accounts_on_device_7d": 4,
        "accounts_on_ip_1h": 0,
        "accounts_on_ip_24h": 0,
        "accounts_on_ip_7d": 0,
        "email_alias_burst": True,
        "email_alias_burst_24h": True,
        "account_age_minutes": 120,
    }
    r = multi_account.score(snap)
    # With soft-OR, c_dev and c_email combine > either alone
    assert r.confidence > 0.75  # tune to actual sat after cal load; must be > max-alone
```

Implementer: compute expected with current sat params; assert `r.confidence == soft_or([c_dev, c_ip, c_email])` style by importing `soft_or`/`sat` in the test for exact equality.

- [ ] **Step 2: Run — expect FAIL** (still using `max`)

- [ ] **Step 3: Rewrite scorers**

`multi_account.py` pattern:

```python
from loyalty_abuse.mathutil import sat, soft_or

def score(snapshot):
    cal = load_calibration()
    # Prefer burst window for farm, 7d for slow-roll: take soft-OR of window sats per channel
    c_dev = soft_or([
        sat(float(snapshot.get("accounts_on_device_1h") or 0), *sat_params("accounts_on_device_1h")),
        sat(float(snapshot.get("accounts_on_device_24h") or 0), *sat_params("accounts_on_device_24h")),
        sat(float(snapshot.get("accounts_on_device_7d") or 0), *sat_params("accounts_on_device_7d")),
    ])
    # If 1h sat keys missing in cal during partial migrate, fall back to 24h params for all — prefer full cal in Task 4 first.
```

**Order note:** If Task 4 calibration is not yet present, implement Task 4 **before** Step 3 of this task, or temporarily reuse 24h sat params for 1h/7d with distinct knees in v1_2 JSON.

Recommended execution order: finish Task 4 calibration JSON first if needed, then this task. **If blocked, swap: do Task 4 then Task 3.**

`promo_stack`: `soft_or([c_stack, c_disc])`  
`bot_redeem`: `soft_or([c_r, c_s])` then young multiplier  
`code_leak`: `soft_or` of 1h/24h/7d code user sats  
`referral_self_deal`: keep discrete confidences; soft-OR channels (device, payment) instead of picking max/both constant only — if both, soft_or([0.9, 0.85]) or keep `referral_both_c` as override when both true (document chosen behavior: **if both → `referral_both_c`, else soft_or of active channels**)

- [ ] **Step 4: pytest typologies + evaluate smoke**

```bash
python -m pytest tests/test_soft_or_typologies.py tests/test_evaluate.py -v
```

- [ ] **Step 5: Commit**

```bash
git add src/loyalty_abuse/typologies/ tests/test_soft_or_typologies.py
git commit -m "feat: soft-OR typology evidence channels"
```

---

### Task 4: `friction_v1_2` calibration + score contract

**Files:**
- Create: `src/loyalty_abuse/calibration/friction_v1_2.json`
- Modify: `src/loyalty_abuse/calibration/__init__.py` (point `_CAL_PATH` at v1_2; validate `blend == "weighted_sum"`)
- Modify: `src/loyalty_abuse/score.py` (remove max_weight_normalize)
- Modify: `src/loyalty_abuse/schema.py` (`POLICY_VERSION = "friction_v1_2"`)
- Modify: `src/loyalty_abuse/typologies/_contrib.py` (points stay `round(100*w*c)`)
- Create: `tests/test_score_contract.py`
- Modify: `tests/test_calibration.py`, `tests/fixtures/golden_tiers.json`, contracts as needed

**Interfaces:**
- Consumes: weights sum 1, typology confidences
- Produces: `score = round(100 * clip(Σ w_i c_i))`; `sum(points) ≈ score` ±1

- [ ] **Step 1: Write score contract test**

```python
from loyalty_abuse import evaluate
from loyalty_abuse.features import FeatureStore
from loyalty_abuse.schema import EventEnvelope, EventType

def test_points_sum_matches_score():
    store = FeatureStore()
    # reuse hard_ato_chain or block_stacked fixture events from golden
    # ... observe all but last, evaluate last ...
    d = evaluate(last_event, store)
    pts = sum(t.points for t in d.typology_breakdown)
    # inactive typologies may be omitted from breakdown — contract is sum(active points) ≈ score
    # Also include zero-confidence typologies? Spec: sum of contributions.
    # Implement evaluate to either include all typologies in breakdown or compute points from all scorers.
    assert abs(pts - d.score) <= 1
    assert d.policy_version == "friction_v1_2"
```

**Important:** Today `evaluate` only puts `active` (c>0) in breakdown. Points for inactive are 0, so sum(active points) must equal score. With `weighted_sum` and no max_w rescale, `round(100*Σ w c)` may differ from `Σ round(100 w c)` by >1 in edge cases — contract allows ±1; if flaky, change score to `sum(points)` clipped to 0..100 from all scorers (preferred honesty):

```python
results = [s(snap) for s in ALL_SCORERS]
score = int(max(0, min(100, sum(r.points for r in results))))
# or: score = int(round(100 * clip(sum(w*c)))) and points from same floats before round
```

Pick **one** and test it. Recommended: compute `weighted = Σ w*c`, `score = round(100*clip(weighted))`, `points_i = round(100*w_i*c_i)`, assert abs(sum(points)-score)<=1 on goldens + random snaps.

- [ ] **Step 2: Run — expect FAIL** (still v1_1 / max_weight_normalize)

- [ ] **Step 3: Add `friction_v1_2.json`**

```json
{
  "policy_version": "friction_v1_2",
  "blend": "weighted_sum",
  "weights": {
    "ato_redeem": 0.22,
    "multi_account": 0.18,
    "bot_redeem": 0.18,
    "referral_self_deal": 0.14,
    "code_leak": 0.14,
    "promo_stack": 0.14
  },
  "bands": {
    "allow_max": 24,
    "throttle_max": 44,
    "soft_max": 64,
    "hard_max": 84
  },
  "sat": {
    "accounts_on_device_1h": { "a": 2, "b": 4 },
    "accounts_on_device_24h": { "a": 2, "b": 5 },
    "accounts_on_device_7d": { "a": 3, "b": 8 },
    "accounts_on_ip_1h": { "a": 3, "b": 8 },
    "accounts_on_ip_24h": { "a": 3, "b": 10 },
    "accounts_on_ip_7d": { "a": 5, "b": 20 },
    "redeem_count_5m": { "a": 4, "b": 16 },
    "signup_count_5m": { "a": 3, "b": 12 },
    "code_unique_users_1h": { "a": 8, "b": 25 },
    "code_unique_users_24h": { "a": 15, "b": 50 },
    "code_unique_users_7d": { "a": 25, "b": 80 },
    "stack_depth": { "a": 2, "b": 5 },
    "discount_depth": { "a": 30, "b": 70 }
  },
  "hard_floor": { "redeem_5m": 20, "signup_5m": 15 },
  "young_account_minutes": 60,
  "young_bot_mult": 1.15,
  "young_multi_mult": 1.1,
  "ato_confidence": 0.85,
  "email_burst_confidence": 0.75,
  "referral_shared_device_c": 0.9,
  "referral_shared_payment_c": 0.85,
  "referral_both_c": 1.0
}
```

Update loader:

```python
_CAL_PATH = Path(__file__).with_name("friction_v1_2.json")
# after load:
if data.get("blend") != "weighted_sum":
    raise CalibrationError("friction_v1_2 requires blend=weighted_sum")
```

`score.py`:

```python
weighted = sum(float(weights.get(r.id) or 0.0) * float(r.confidence) for r in results)
score = int(round(100.0 * clip(weighted)))
# remove max_w division
```

- [ ] **Step 4: Retune goldens + full pytest**

```bash
python -m pytest -q
```

Update `golden_tiers.json` expected_friction only when mathematically required; keep reason substrings stable.

- [ ] **Step 5: Commit**

```bash
git add src/loyalty_abuse/calibration/ src/loyalty_abuse/score.py \
  src/loyalty_abuse/schema.py src/loyalty_abuse/typologies/_contrib.py \
  tests/test_score_contract.py tests/test_calibration.py \
  tests/fixtures/golden_tiers.json contracts/
git commit -m "feat: friction_v1_2 weighted_sum score contract"
```

---

### Task 5: Adversarial eval suite (primary adversarial suite proof)

**Files:**
- Create: `scripts/adversarial_eval.py`
- Create: `tests/fixtures/adversarial_slices.json` (optional compact journeys)
- Create: `tests/test_adversarial_eval.py`
- Modify: `README.md` (adversarial gate claim language)
- Modify: `.gitignore` if writing `artifacts/adversarial_*.json`

**Interfaces:**
- Consumes: `evaluate`, `FeatureStore`, EventEnvelope
- Produces: JSON report + process exit 0 iff all slice bounds pass

**Slice bounds (publish in script + report):**

| Slice | Metric | Bound |
|---|---|---|
| `household_fp` | allow rate on legit shared-device family (2–3 accts, aged, low velocity) | allow_rate ≥ 0.85 |
| `device_rotation` | catch rate (friction ≥ soft_challenge) when attacker rotates device_id each signup/redeem | catch_rate ≥ 0.60 |
| `slow_multi_acct` | catch rate when 5 accounts on same device spaced >24h apart over 7d | catch_rate ≥ 0.70 |
| `sequential_promo` | catch rate when stack builds across events (not one payload) | catch_rate ≥ 0.50 |
| `ato_known_device` | catch rate for login→profile→redeem on **same** device without new_device/new_geo but with impossible velocity / email change — **if** v1.2 still requires new_device\|new_geo for ato_chain, this slice may document expected miss and instead require `intel` placeholder skip; **implementer must either (a) extend ATO features for known-device impossible pattern in Phase 1 or (b) mark slice as `xfail`/informational.** Spec wants the slice — **prefer (a) minimal: flag `ato_chain` when profile_update sensitive fields + redeem ≤30m after login even without new_device, with lower confidence `ato_known_device_confidence` (e.g. 0.55) so household is not blocked.** |

- [ ] **Step 1: Write `tests/test_adversarial_eval.py` that imports runner**

```python
from scripts.adversarial_eval import run_suite

def test_adversarial_suite_passes():
    report = run_suite(seed=42)
    assert report["gates_pass"] is True
```

(If scripts not importable, put runner in `src/loyalty_abuse/eval/adversarial.py` and thin CLI in scripts — **prefer** `src/loyalty_abuse/eval/adversarial.py` for importability.)

- [ ] **Step 2: Run — expect FAIL** (module missing)

- [ ] **Step 3: Implement suite**

Create `src/loyalty_abuse/eval/adversarial.py` with `run_suite(seed: int = 42) -> dict` generating N journeys per slice (N≥50), scoring final redeem/referral, computing metrics vs bounds.

CLI:

```bash
python scripts/adversarial_eval.py --seed 42 --out artifacts/adversarial_v1_2.json
```

Exit code 1 if `gates_pass` is false.

- [ ] **Step 4: Green suite + unit tests**

```bash
python -m pytest tests/test_adversarial_eval.py -v
python scripts/adversarial_eval.py --seed 42 --out artifacts/adversarial_v1_2.json
```

If bounds fail: retune sat knees / ATO known-device confidence once; re-run seed 42; do not weaken bounds below table without updating the program spec.

- [ ] **Step 5: README + commit**

README: state that adversarial gate proof is `scripts/adversarial_eval.py`; synth 500k is regression-only.

```bash
git add src/loyalty_abuse/eval/ scripts/adversarial_eval.py \
  tests/test_adversarial_eval.py README.md
git commit -m "test: add adversarial eval suite as adversarial gate gate"
```

---

### Task 6: Phase 1 closeout

**Files:** README / short note in program spec status if desired

- [ ] **Step 1: Full verification**

```bash
python -m pytest -q
python scripts/adversarial_eval.py --seed 42 --out artifacts/adversarial_v1_2.json
```

Expected: pytest green; adversarial `gates_pass: true`.

- [ ] **Step 2: Commit any leftover golden/README fixes**

```bash
git add -u && git status -sb
# commit only if there are Phase-1 leftovers
```

- [ ] **Step 3: Stop — do not start Phase 2 without a Phase 2 plan**

---

## Spec coverage (Phase 1 only)

| Spec requirement | Task |
|---|---|
| Adversarial + household eval; CI can fail | 5 |
| 500k synth demoted (README) | 5 |
| Drop max_weight_normalize; weighted_sum | 4 |
| points ≡ score ±1 | 4 |
| soft-OR inside typologies | 1, 3 |
| Multi-window 1h/24h/7d | 2, 3, 4 (sat keys) |
| policy_version friction_v1_2 | 4 |
| No graph / $ / Incognia / ECE | — out of scope |
| Observe-only in evaluate | preserved (no change) |

## Self-review notes

- Task 3 depends on Task 4 sat keys — execute Task 4 calibration file before typology window sats, or use fallback params.
- ATO known-device slice needs a minimal feature extension in Task 5 (or 3); do not silently skip.
- Phase 2/3 intentionally absent from this plan.
)
