# Phase 3 — device-intel path Trajectory (Incognia + Ops Loop) Implementation Plan

> **Privacy:** Letter-grade maturity ratings are private ([`docs/compliance/RATINGS_PRIVATE.md`](../../compliance/RATINGS_PRIVATE.md)). This document uses capability language only.


> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the device-intel path *path*: Incognia adapter (fixture + live-gated), challenge outcome ingest, optional consortium stub, continual adversarial drift report, and ops metrics — without claiming live device-intel readiness from synth alone.

**Architecture:** Vendor code lives under `adapters/incognia/` with optional `incognia-python`. Host/API fetches intel → writes normalized signals onto `EventEnvelope.payload` (`device_intel.*`) before `evaluate()`. Core reads only normalized payload keys / a tiny protocol — **never** `import incognia`. Challenge outcomes POST to API and join by `decision_id`/`event_id` for labels. Consortium is a no-op interface. Ops metrics extend analytics.

**Tech Stack:** Python 3.12, existing FastAPI/SQLite stack; optional dep `incognia-python` (extras `[incognia]`); fixture JSON for offline

**Spec:** `docs/superpowers/specs/2026-08-05-maturity-program-design.md` (Phase 3)

**Base:** Branch `feat/phase-3-device-intel` from current Phase 2 tip (`feat/phase-2-technical-readiness`).

## Global Constraints

- Core `loyalty_abuse` never imports FastAPI, Incognia, or Tarka.
- Only `evaluate()` observes the scored event.
- No `review` friction action.
- Keep `friction_v2_0` score contract (weighted_sum, points≈score) unless a tiny bump is required — prefer payload + policy floor without version bump.
- Live Incognia calls only when `INCOGNIA_CLIENT_ID`, `INCOGNIA_CLIENT_SECRET`, `INCOGNIA_POLICY_ID` set; else fixture/replay.
- Fail-closed for redeem when tenant `incognia_required=true` and call fails; else degrade with `intel.incognia_unavailable`.
- Do not claim live device-intel readiness from fixtures/synth.
- Phase 1 adversarial + Phase 2 suites must stay green.

## File Structure

| Path | Role |
|---|---|
| `adapters/incognia/__init__.py` | Public: `fetch_signals(...)`, `IncogniaSignals` |
| `adapters/incognia/client.py` | Live client wrapper around `IncogniaAPI` |
| `adapters/incognia/normalize.py` | Raw assessment → `IncogniaSignals` |
| `adapters/incognia/fixtures/login_low_risk.json` | Pinned fixture |
| `adapters/incognia/fixtures/login_high_risk.json` | Pinned fixture |
| `adapters/incognia/README.md` | Env vars, modes, mapping table |
| `pyproject.toml` | optional-dependencies `incognia = ["incognia-python>=3.7"]` |
| `src/loyalty_abuse/device_intel.py` | Apply signals to payload; friction floor from intel |
| `src/loyalty_abuse/score.py` / `policy.py` | Optional intel hard floor (high_risk → ≥ hard_challenge) |
| `src/loyalty_abuse_api/app.py` | Enrich evaluate with Incognia; challenge outcome endpoint |
| `src/loyalty_abuse_api/db.py` | `challenge_outcomes`, `intel_calls` tables |
| `src/loyalty_abuse_api/analytics.py` | Ops metrics |
| `adapters/consortium/__init__.py` | No-op `lookup_badness(hashes) -> {}` |
| `scripts/drift_reeval.py` | Re-run adversarial; fail if slice below bound |
| `tests/adapters/test_incognia.py`, `tests/test_device_intel.py`, `tests/test_challenge_outcomes.py`, `tests/test_ops_metrics.py` | |

---

### Task 0: Branch + baseline green

- [ ] Create `feat/phase-3-device-intel` from Phase 2 tip; pytest + adversarial green.

```bash
cd /Users/pamu/Documents/GitHub/loyalty-abuse
git checkout feat/phase-2-technical-readiness
git checkout -b feat/phase-3-device-intel
PYTHONPATH=src python3 -m pytest -q
PYTHONPATH=src python3 scripts/adversarial_eval.py --seed 42 --out artifacts/adversarial_p3_baseline.json
```

---

### Task 1: IncogniaSignals + normalize + fixtures

**Files:** `adapters/incognia/*`, `tests/adapters/test_incognia.py`

**Interfaces:**

```python
@dataclass(frozen=True)
class IncogniaSignals:
    risk_assessment: str  # low_risk | high_risk | unknown_risk
    tamper_suspected: bool
    emulator: bool
    gps_spoofing: bool
    location_permission_enabled: bool | None
    device_fraud_reputation: str | None
    known_account: bool | None
    raw_id: str | None
    source: str  # fixture | live | unavailable

def normalize_assessment(raw: dict, *, source: str) -> IncogniaSignals: ...
```

**Fixture shape (snake_case, pinned from public SDK docs):**

```json
{
  "id": "fix-login-low",
  "risk_assessment": "low_risk",
  "evidence": {
    "device_integrity": {
      "emulator": false,
      "gps_spoofing": false,
      "probable_root": false,
      "from_official_store": true
    },
    "location_services": {
      "location_permission_enabled": true,
      "location_sensors_enabled": true
    },
    "device_fraud_reputation": "allowed",
    "known_account": true
  }
}
```

High-risk fixture: `risk_assessment: high_risk`, `probable_root: true` and/or `emulator: true`.

- [ ] **Step 1:** Failing tests for normalize low/high fixtures
- [ ] **Step 2:** Implement normalize + fixtures + README mapping table
- [ ] **Step 3:** Commit `feat: Incognia signal normalize and fixtures`

---

### Task 2: fetch_signals — fixture vs live-gated client

**Files:** `adapters/incognia/client.py`, `__init__.py`, `pyproject.toml`, tests

```python
def fetch_signals(
    *,
    request_token: str,
    account_id: str,
    event_type: str,
    external_id: str | None = None,
    fixture_name: str | None = None,
) -> IncogniaSignals:
    """Live if env creds present; else load fixture (default login_low_risk)."""
```

Live path (only if `incognia` extra installed AND env set):

```python
from incognia.api import IncogniaAPI
api = IncogniaAPI(client_id, client_secret)
# login/redeem-adjacent → register_login; signup → register_new_signup
raw = api.register_login(request_token, account_id, external_id, policy_id=policy_id)
```

On ImportError / timeout / 5xx: return `IncogniaSignals(..., risk_assessment="unknown_risk", source="unavailable")` — do not raise from fetch unless caller asks.

- [ ] Unit test: without env → fixture source
- [ ] Unit test: mock live client returns normalized high_risk
- [ ] Commit `feat: Incognia fetch_signals fixture and live gate`

---

### Task 3: Core device_intel + friction floor

**Files:** `src/loyalty_abuse/device_intel.py`, wire `score.py`/`features.py`/`policy.py`, tests

```python
def apply_to_payload(payload: dict, signals: IncogniaSignals) -> dict:
    # sets device_intel.risk_assessment, .tamper_suspected, .emulator, ...

def intel_force_hard_floor(snapshot_or_payload: dict) -> bool:
    # True if risk_assessment == high_risk OR tamper_suspected OR emulator
```

`evaluate()` / FeatureStore snapshot: if payload has `device_intel.*`, set `force_hard_floor` OR a new `intel_hard_floor` that policy treats like hard floor (at least `hard_challenge`). Add reason `intel.incognia_high_risk` when floor applied.

Also: if payload has `device_intel.unavailable` / missing when required — that is API concern (Task 4); core only reacts to present signals.

- [ ] Test: high_risk payload → hard_challenge even with low behavioral score
- [ ] Test: low_risk → no intel floor
- [ ] Commit `feat: device intel friction floor in core`
- [ ] Ensure `tests/test_library_no_fastapi_import.py` still passes; add assert no `incognia` import under `src/loyalty_abuse`

---

### Task 4: API enrich + fail-closed / fail-open

**Files:** `loyalty_abuse_api/app.py`, `db.py`, tests

Before `_run_evaluate` scoring path:

1. If event payload has `request_token` (or `incognia_request_token`):
   - call `adapters.incognia.fetch_signals(...)`
   - log latency/success to `intel_calls` table
   - merge via `apply_to_payload`
2. Tenant flag: read `payload.get("incognia_required")` or env `INCOGNIA_REQUIRED_DEFAULT=false`
3. On `source==unavailable` and required and event type in `{redeem, checkout}`:
   - fail-closed: return Decision with friction `block` (or hard_challenge) + reason `intel.incognia_unavailable` **without** claiming behavioral score honesty — OR short-circuit evaluate with synthetic high floor. Prefer: still call evaluate after injecting `device_intel.risk_assessment=high_risk` + reason already set. Simplest honest approach: inject unavailable marker and set `force_hard_floor` via payload flag `device_intel_force_block=true` that features/score honor.
4. If not required: proceed with reason `intel.incognia_unavailable` only if token was present but call failed.

- [ ] API tests with fixtures (no live network)
- [ ] Commit `feat: API Incognia enrich with fail-closed redeem`

---

### Task 5: Challenge outcome ingest

**Files:** db + app + tests

```http
POST /v1/challenge_outcomes
{
  "decision_id": "dec_...",
  "event_id": "optional",
  "outcome": "passed" | "failed" | "abandoned",
  "ts": "ISO-8601"
}
```

Store in `challenge_outcomes`; do **not** rewrite historical decisions. Analytics can join later for calibration labels.

- [ ] Test round-trip persist + fetch by decision_id
- [ ] Commit `feat: challenge outcome ingest endpoint`

---

### Task 6: Consortium stub + drift re-eval + ops metrics

**Files:** `adapters/consortium/`, `scripts/drift_reeval.py`, analytics, tests, README

1. `lookup_badness(hashes: list[str]) -> dict[str, float]` returns `{}` (no-op).
2. `scripts/drift_reeval.py --seed 42` runs adversarial suite; exit 1 if any slice fails bound; write `artifacts/drift_reeval.json`.
3. Extend `GET /v1/analytics/summary` (or `/v1/analytics/ops`) with:
   - insult_proxy (hard_challenge+rate on allow-labeled shadow if available; else friction mix)
   - expected_loss sum vs allow-all baseline if economics present
   - intel_calls success_rate + p50 latency_ms
   - challenge_outcomes conversion (passed / (passed+failed+abandoned))
4. README: device-intel path *path* shipped; live device-intel readiness needs live Incognia + real challenge labels + weeks of ops.

- [ ] Commit `feat: consortium stub, drift reeval, ops metrics`

---

### Task 7: Phase 3 closeout

- [ ] Full pytest green; adversarial green; drift_reeval exit 0
- [ ] Update program spec status: Phase 3 path complete; live device-intel readiness not claimed
- [ ] Commit `chore: Phase 3 closeout`
- [ ] Stop

---

## Spec coverage (Phase 3)

| Spec item | Task |
|---|---|
| adapters/incognia + normalize + fixtures | 1 |
| Live-gated client / env | 2 |
| Core consumes normalized signals only | 3 |
| Fail-closed / unavailable reason | 4 |
| Challenge outcomes POST | 5 |
| Consortium no-op | 6 |
| Continual adversarial re-eval | 6 |
| Ops metrics | 6 |
| No device-intel path claim from synth | 7 / README |

## Self-review notes

- Fixture field names pinned; update when live sandbox JSON differs.
- Do not add `incognia-python` to required deps.
- Intel floor must not invent `review`.
- Observe-only-in-evaluate preserved (API enriches payload before evaluate).
