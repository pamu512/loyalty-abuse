# QSR Loyalty Abuse Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a standalone rules-first loyalty-abuse scorer with explainable scores, tiered friction (`allow`→`throttle`→`soft_challenge`→`hard_challenge`→`block`), HTTP API, analytics, and offline eval — usable alone or via a thin host adapter (e.g. Tarka later).

**Architecture:** Pure library (`loyalty_abuse`) owns schema, features, typologies, policy, and `evaluate()`. FastAPI adapter (`loyalty_abuse_api`) owns SQLite event/decision persistence and fail-closed audit-before-200. Optional `adapters/tarka/` is deferred (stub README only). Dashboard + notebook read audit/analytics.

**Tech Stack:** Python 3.12, pydantic v2, FastAPI, uvicorn, SQLite (stdlib), pytest, httpx, docker compose

**Spec:** `docs/superpowers/specs/2026-08-04-qsr-loyalty-abuse-design.md`

## Global Constraints

- Core library MUST NOT import FastAPI, uvicorn, docker, or any host SDK (including Tarka).
- Friction enum is exactly: `allow`, `throttle`, `soft_challenge`, `hard_challenge`, `block` — no `review`.
- Every HTTP evaluate success requires a persisted decision row first; persist failure → HTTP 503.
- Score is additive 0–100 with `typology_breakdown[]` and `reasons[]` on every Decision.
- `policy_version` and `schema_version` recorded on every Decision (`friction_v1`, `1`).
- Standalone must run with `docker compose up` (or `uvicorn`) with no host platform installed.
- TDD: write failing test → run fail → implement → run pass → commit, per task.

## File Structure

| Path | Responsibility |
|---|---|
| `pyproject.toml` | Package metadata, deps, pytest config |
| `README.md` | Standalone quickstart |
| `contracts/*.schema.json` | Stable JSON schemas |
| `src/loyalty_abuse/__init__.py` | Public exports: `evaluate`, types |
| `src/loyalty_abuse/schema.py` | Event / Decision / Friction pydantic models |
| `src/loyalty_abuse/policy.py` | Score → friction mapping + hard overrides |
| `src/loyalty_abuse/features.py` | In-memory feature store + `FeatureSnapshot` |
| `src/loyalty_abuse/typologies/*.py` | Six scorers + registry |
| `src/loyalty_abuse/score.py` | `evaluate(event, store, policy) -> Decision` |
| `src/loyalty_abuse_api/app.py` | FastAPI routes |
| `src/loyalty_abuse_api/db.py` | SQLite events + decisions |
| `src/loyalty_abuse_api/analytics.py` | Summary aggregates |
| `static/index.html` | Minimal analytics dashboard |
| `scripts/seed_demo.py` | Accertify pattern seed generator |
| `notebooks/offline_eval.py` | Threshold / reason coverage script (`.py` so CI-friendly) |
| `adapters/tarka/README.md` | Optional adapter notes only (no code in v1) |
| `docker-compose.yml` / `Dockerfile` | Standalone run |
| `tests/...` | Unit, golden, API contract |

---

### Task 1: Project scaffold + schema types

**Files:**
- Create: `pyproject.toml`
- Create: `src/loyalty_abuse/__init__.py`
- Create: `src/loyalty_abuse/schema.py`
- Create: `tests/test_schema.py`
- Create: `README.md` (stub quickstart; expand in Task 9)

**Interfaces:**
- Consumes: nothing
- Produces: `FrictionAction`, `EventType`, `EventEnvelope`, `TypologyResult`, `Decision` in `loyalty_abuse.schema`; `SCHEMA_VERSION = 1`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_schema.py
from loyalty_abuse.schema import Decision, EventEnvelope, FrictionAction, SCHEMA_VERSION


def test_friction_actions_exact_set():
    assert {a.value for a in FrictionAction} == {
        "allow",
        "throttle",
        "soft_challenge",
        "hard_challenge",
        "block",
    }
    assert "review" not in {a.value for a in FrictionAction}


def test_event_envelope_roundtrip():
    e = EventEnvelope(
        event_id="evt_1",
        tenant_id="t1",
        ts="2026-08-04T00:00:00Z",
        type="redeem",
        account_id="acct_1",
        session_id="sess_1",
        device_id="dev_1",
        ip="1.2.3.4",
        payload={"reward_id": "r1", "points": 100, "offer_ids": ["o1"], "channel": "app"},
    )
    data = e.model_dump()
    assert EventEnvelope.model_validate(data).event_id == "evt_1"


def test_decision_requires_reasons_and_breakdown():
    d = Decision(
        decision_id="dec_1",
        event_id="evt_1",
        score=0,
        friction=FrictionAction.allow,
        reasons=[],
        typology_breakdown=[],
        features_snapshot={},
        policy_version="friction_v1",
        schema_version=SCHEMA_VERSION,
    )
    assert d.schema_version == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/pamu/Documents/GitHub/loyalty-abuse && python -m pytest tests/test_schema.py -v`
Expected: FAIL (package / module not found)

- [ ] **Step 3: Write minimal implementation**

`pyproject.toml`:

```toml
[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "loyalty-abuse"
version = "0.1.0"
description = "Standalone QSR loyalty abuse scorer with explainable friction"
requires-python = ">=3.12"
dependencies = [
  "pydantic>=2.7",
  "fastapi>=0.115",
  "uvicorn[standard]>=0.30",
  "httpx>=0.27",
]

[project.optional-dependencies]
dev = ["pytest>=8.0", "ruff>=0.6"]

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
```

`src/loyalty_abuse/schema.py`:

```python
from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

SCHEMA_VERSION = 1
POLICY_VERSION = "friction_v1"


class FrictionAction(str, Enum):
    allow = "allow"
    throttle = "throttle"
    soft_challenge = "soft_challenge"
    hard_challenge = "hard_challenge"
    block = "block"


class EventType(str, Enum):
    signup = "signup"
    login = "login"
    profile_update = "profile_update"
    referral = "referral"
    offer_enroll = "offer_enroll"
    redeem = "redeem"
    checkout = "checkout"


class EventEnvelope(BaseModel):
    event_id: str
    tenant_id: str
    ts: str
    type: EventType
    account_id: str
    session_id: str
    device_id: str
    ip: str
    email: str | None = None
    phone: str | None = None
    payment_instrument_hash: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class TypologyResult(BaseModel):
    id: str
    points: int
    reasons: list[str] = Field(default_factory=list)


class Decision(BaseModel):
    decision_id: str
    event_id: str
    score: int
    friction: FrictionAction
    reasons: list[str]
    typology_breakdown: list[TypologyResult]
    features_snapshot: dict[str, Any]
    policy_version: str = POLICY_VERSION
    schema_version: int = SCHEMA_VERSION
```

`src/loyalty_abuse/__init__.py`:

```python
from loyalty_abuse.schema import (
    SCHEMA_VERSION,
    POLICY_VERSION,
    Decision,
    EventEnvelope,
    EventType,
    FrictionAction,
    TypologyResult,
)

__all__ = [
    "SCHEMA_VERSION",
    "POLICY_VERSION",
    "Decision",
    "EventEnvelope",
    "EventType",
    "FrictionAction",
    "TypologyResult",
    "evaluate",
]

def __getattr__(name: str):
    if name == "evaluate":
        from loyalty_abuse.score import evaluate
        return evaluate
    raise AttributeError(name)
```

`README.md` stub: one paragraph goal + "see docs/superpowers/specs/…".

- [ ] **Step 4: Run test to verify it passes**

Run: `pip install -e ".[dev]" && pytest tests/test_schema.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml README.md src/loyalty_abuse/__init__.py src/loyalty_abuse/schema.py tests/test_schema.py
git commit -m "feat: add schema types and project scaffold"
```

---

### Task 2: Friction policy

**Files:**
- Create: `src/loyalty_abuse/policy.py`
- Create: `tests/test_policy.py`

**Interfaces:**
- Consumes: `FrictionAction` from schema
- Produces: `FrictionPolicy` with `action_for(score: int, *, force_hard_floor: bool = False) -> FrictionAction`; defaults per spec bands; `POLICY_VERSION`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_policy.py
from loyalty_abuse.policy import FrictionPolicy
from loyalty_abuse.schema import FrictionAction


def test_default_bands():
    p = FrictionPolicy()
    assert p.action_for(0) == FrictionAction.allow
    assert p.action_for(24) == FrictionAction.allow
    assert p.action_for(25) == FrictionAction.throttle
    assert p.action_for(44) == FrictionAction.throttle
    assert p.action_for(45) == FrictionAction.soft_challenge
    assert p.action_for(64) == FrictionAction.soft_challenge
    assert p.action_for(65) == FrictionAction.hard_challenge
    assert p.action_for(84) == FrictionAction.hard_challenge
    assert p.action_for(85) == FrictionAction.block
    assert p.action_for(100) == FrictionAction.block


def test_hard_override_floor():
    p = FrictionPolicy()
    assert p.action_for(10, force_hard_floor=True) == FrictionAction.hard_challenge
    assert p.action_for(90, force_hard_floor=True) == FrictionAction.block
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_policy.py -v`
Expected: FAIL (`FrictionPolicy` not found)

- [ ] **Step 3: Write minimal implementation**

```python
# src/loyalty_abuse/policy.py
from __future__ import annotations

from dataclasses import dataclass

from loyalty_abuse.schema import FrictionAction, POLICY_VERSION


@dataclass(frozen=True)
class FrictionPolicy:
    allow_max: int = 24
    throttle_max: int = 44
    soft_max: int = 64
    hard_max: int = 84
    version: str = POLICY_VERSION

    def action_for(self, score: int, *, force_hard_floor: bool = False) -> FrictionAction:
        s = max(0, min(100, int(score)))
        if s <= self.allow_max:
            action = FrictionAction.allow
        elif s <= self.throttle_max:
            action = FrictionAction.throttle
        elif s <= self.soft_max:
            action = FrictionAction.soft_challenge
        elif s <= self.hard_max:
            action = FrictionAction.hard_challenge
        else:
            action = FrictionAction.block
        if force_hard_floor:
            order = [
                FrictionAction.allow,
                FrictionAction.throttle,
                FrictionAction.soft_challenge,
                FrictionAction.hard_challenge,
                FrictionAction.block,
            ]
            if order.index(action) < order.index(FrictionAction.hard_challenge):
                return FrictionAction.hard_challenge
        return action
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_policy.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/loyalty_abuse/policy.py tests/test_policy.py
git commit -m "feat: add friction policy bands and hard floor"
```

---

### Task 3: Feature store

**Files:**
- Create: `src/loyalty_abuse/features.py`
- Create: `tests/test_features.py`

**Interfaces:**
- Consumes: `EventEnvelope`
- Produces: `FeatureStore` with `observe(event) -> None` and `snapshot(event) -> dict[str, Any]` containing at least:
  - `accounts_on_device_24h`, `accounts_on_ip_24h`
  - `email_alias_burst` (bool)
  - `referral_shared_device`, `referral_shared_payment` (bool)
  - `stack_depth`, `discount_depth`
  - `redeem_count_5m`, `signup_count_5m` (for account or device as documented in code)
  - `code_unique_users_24h`
  - `account_age_minutes`, `minutes_signup_to_event`
  - `ato_chain` (bool), `minutes_login_to_redeem`
  - `force_hard_floor` (bool) — true when ATO chain or extreme bot velocity

Use in-memory structures only (no SQLite in core). Window math: parse `ts` as aware UTC; keep event lists per key and count within windows.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_features.py
from loyalty_abuse.features import FeatureStore
from loyalty_abuse.schema import EventEnvelope, EventType


def _e(**kwargs):
    base = dict(
        event_id="e1",
        tenant_id="t1",
        ts="2026-08-04T12:00:00Z",
        type=EventType.signup,
        account_id="a1",
        session_id="s1",
        device_id="d1",
        ip="10.0.0.1",
        email="user@example.com",
        payload={},
    )
    base.update(kwargs)
    return EventEnvelope(**base)


def test_shared_device_linkage():
    store = FeatureStore()
    store.observe(_e(event_id="1", account_id="a1", device_id="devX", type=EventType.signup, ts="2026-08-04T12:00:00Z"))
    store.observe(_e(event_id="2", account_id="a2", device_id="devX", type=EventType.signup, ts="2026-08-04T12:01:00Z"))
    snap = store.snapshot(_e(event_id="3", account_id="a2", device_id="devX", type=EventType.redeem, ts="2026-08-04T12:02:00Z", payload={"offer_ids": []}))
    assert snap["accounts_on_device_24h"] >= 2


def test_ato_chain_flag():
    store = FeatureStore()
    store.observe(_e(event_id="1", type=EventType.signup, ts="2026-08-04T10:00:00Z", account_id="a1", device_id="old"))
    store.observe(
        _e(
            event_id="2",
            type=EventType.login,
            ts="2026-08-04T12:00:00Z",
            account_id="a1",
            device_id="new",
            payload={"success": True, "new_device": True, "geo": "XX"},
        )
    )
    store.observe(
        _e(
            event_id="3",
            type=EventType.profile_update,
            ts="2026-08-04T12:01:00Z",
            account_id="a1",
            device_id="new",
            payload={"fields_changed": ["email"]},
        )
    )
    snap = store.snapshot(
        _e(
            event_id="4",
            type=EventType.redeem,
            ts="2026-08-04T12:02:00Z",
            account_id="a1",
            device_id="new",
            payload={"reward_id": "r", "points": 50, "offer_ids": [], "channel": "app"},
        )
    )
    assert snap["ato_chain"] is True
    assert snap["force_hard_floor"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_features.py -v`
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

```python
# src/loyalty_abuse/features.py
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from loyalty_abuse.schema import EventEnvelope, EventType


def _parse_ts(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(timezone.utc)


def _email_root(email: str | None) -> str | None:
    if not email or "@" not in email:
        return None
    local, domain = email.lower().split("@", 1)
    local = local.split("+", 1)[0].replace(".", "")
    return f"{local}@{domain}"


class FeatureStore:
    def __init__(self) -> None:
        self._events: list[EventEnvelope] = []

    def observe(self, event: EventEnvelope) -> None:
        self._events.append(event)

    def _in_window(self, now: datetime, window: timedelta, pred) -> list[EventEnvelope]:
        start = now - window
        out = []
        for e in self._events:
            et = _parse_ts(e.ts)
            if et < start or et > now:
                continue
            if pred(e):
                out.append(e)
        return out

    def snapshot(self, event: EventEnvelope) -> dict[str, Any]:
        now = _parse_ts(event.ts)
        d24 = timedelta(hours=24)
        d5m = timedelta(minutes=5)
        on_device = self._in_window(now, d24, lambda e: e.device_id == event.device_id and e.tenant_id == event.tenant_id)
        on_ip = self._in_window(now, d24, lambda e: e.ip == event.ip and e.tenant_id == event.tenant_id)
        accounts_device = {e.account_id for e in on_device}
        accounts_ip = {e.account_id for e in on_ip}

        roots: dict[str, set[str]] = defaultdict(set)
        for e in self._in_window(now, d24, lambda e: e.tenant_id == event.tenant_id):
            root = _email_root(e.email)
            if root:
                roots[root].add(e.account_id)
        email_alias_burst = any(len(v) >= 3 for v in roots.values())

        referral_shared_device = False
        referral_shared_payment = False
        if event.type == EventType.referral:
            ref = str(event.payload.get("referrer_id") or "")
            ree = str(event.payload.get("referee_id") or event.account_id)
            devices = {}
            pays = {}
            for e in self._events:
                if e.tenant_id != event.tenant_id:
                    continue
                devices[e.account_id] = e.device_id
                if e.payment_instrument_hash:
                    pays[e.account_id] = e.payment_instrument_hash
            referral_shared_device = bool(ref and ree and devices.get(ref) and devices.get(ref) == devices.get(ree))
            referral_shared_payment = bool(ref and ree and pays.get(ref) and pays.get(ref) == pays.get(ree))

        offers = list(event.payload.get("offer_ids") or [])
        promos = list(event.payload.get("promo_codes") or [])
        loyalty = list(event.payload.get("loyalty_applied") or [])
        stack_depth = len(offers) + len(promos) + len(loyalty)
        discount_depth = float(event.payload.get("discount_pct") or 0)

        redeem_5m = self._in_window(
            now, d5m, lambda e: e.device_id == event.device_id and e.type == EventType.redeem
        )
        signup_5m = self._in_window(
            now, d5m, lambda e: e.device_id == event.device_id and e.type == EventType.signup
        )

        code = None
        if promos:
            code = str(promos[0])
        elif event.payload.get("referral_code"):
            code = str(event.payload["referral_code"])
        code_users: set[str] = set()
        if code:
            for e in self._in_window(now, d24, lambda e: e.tenant_id == event.tenant_id):
                plist = list(e.payload.get("promo_codes") or [])
                if code in plist or e.payload.get("referral_code") == code:
                    code_users.add(e.account_id)

        acct_events = [e for e in self._events if e.account_id == event.account_id and e.tenant_id == event.tenant_id]
        acct_events_sorted = sorted(acct_events, key=lambda e: _parse_ts(e.ts))
        signup_ts = next(( _parse_ts(e.ts) for e in acct_events_sorted if e.type == EventType.signup), None)
        account_age_minutes = (now - signup_ts).total_seconds() / 60.0 if signup_ts else 0.0
        minutes_signup_to_event = account_age_minutes

        ato_chain = False
        minutes_login_to_redeem = None
        recent = [e for e in acct_events_sorted if _parse_ts(e.ts) <= now]
        for i, e in enumerate(recent):
            if e.type != EventType.login:
                continue
            if not (e.payload.get("new_device") or e.payload.get("geo")):
                continue
            login_t = _parse_ts(e.ts)
            prof = next(
                (
                    p
                    for p in recent[i + 1 :]
                    if p.type == EventType.profile_update and (_parse_ts(p.ts) - login_t) <= timedelta(minutes=30)
                ),
                None,
            )
            if not prof:
                continue
            red = next(
                (
                    r
                    for r in recent
                    if r.type in {EventType.redeem, EventType.checkout}
                    and _parse_ts(r.ts) >= _parse_ts(prof.ts)
                    and (_parse_ts(r.ts) - login_t) <= timedelta(minutes=30)
                ),
                None,
            )
            if red or event.type in {EventType.redeem, EventType.checkout}:
                ato_chain = True
                minutes_login_to_redeem = (now - login_t).total_seconds() / 60.0
                break

        force_hard = ato_chain or len(redeem_5m) >= 20 or len(signup_5m) >= 15
        return {
            "accounts_on_device_24h": len(accounts_device),
            "accounts_on_ip_24h": len(accounts_ip),
            "email_alias_burst": email_alias_burst,
            "referral_shared_device": referral_shared_device,
            "referral_shared_payment": referral_shared_payment,
            "stack_depth": stack_depth,
            "discount_depth": discount_depth,
            "redeem_count_5m": len(redeem_5m),
            "signup_count_5m": len(signup_5m),
            "code_unique_users_24h": len(code_users),
            "account_age_minutes": account_age_minutes,
            "minutes_signup_to_event": minutes_signup_to_event,
            "ato_chain": ato_chain,
            "minutes_login_to_redeem": minutes_login_to_redeem,
            "force_hard_floor": force_hard,
        }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_features.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/loyalty_abuse/features.py tests/test_features.py
git commit -m "feat: add in-memory feature store and snapshots"
```

---

### Task 4: Typology scorers + `evaluate()`

**Files:**
- Create: `src/loyalty_abuse/typologies/__init__.py`
- Create: `src/loyalty_abuse/typologies/base.py`
- Create: `src/loyalty_abuse/typologies/multi_account.py`
- Create: `src/loyalty_abuse/typologies/referral_self_deal.py`
- Create: `src/loyalty_abuse/typologies/promo_stack.py`
- Create: `src/loyalty_abuse/typologies/bot_redeem.py`
- Create: `src/loyalty_abuse/typologies/code_leak.py`
- Create: `src/loyalty_abuse/typologies/ato_redeem.py`
- Create: `src/loyalty_abuse/score.py`
- Create: `tests/test_evaluate.py`
- Create: `tests/fixtures/golden_tiers.json`
- Modify: `src/loyalty_abuse/__init__.py` (ensure `evaluate` export works)

**Interfaces:**
- Consumes: `EventEnvelope`, `FeatureStore`, `FrictionPolicy`, `Decision`, `TypologyResult`
- Produces: `evaluate(event: EventEnvelope, store: FeatureStore, policy: FrictionPolicy | None = None) -> Decision`
  - Observes event on store first, snapshots features, runs all scorers, caps sum at 100, maps friction, sets `force_hard_floor` from features, generates `decision_id` as `dec_` + uuid4 hex

Default points (when trigger fires):

| typology | condition | points | reason |
|---|---|---|---|
| `multi_account` | `accounts_on_device_24h >= 3` | 30 | `multi_acct.shared_device_cluster` |
| `multi_account` | `email_alias_burst` | +15 | `multi_acct.email_alias_burst` |
| `referral_self_deal` | `referral_shared_device` | 30 | `referral.shared_device` |
| `referral_self_deal` | `referral_shared_payment` | +20 | `referral.shared_payment` |
| `promo_stack` | `stack_depth >= 3` | 20 | `promo.stack_depth` |
| `promo_stack` | `discount_depth >= 50` | +15 | `promo.discount_depth` |
| `bot_redeem` | `redeem_count_5m >= 10` | 30 | `bot.redeem_velocity` |
| `bot_redeem` | `signup_count_5m >= 8` | +20 | `bot.signup_velocity` |
| `code_leak` | `code_unique_users_24h >= 25` | 25 | `code.unique_user_spike` |
| `ato_redeem` | `ato_chain` | 40 | `ato.login_profile_redeem_chain` |

- [ ] **Step 1: Write the failing test**

```python
# tests/test_evaluate.py
from loyalty_abuse import evaluate
from loyalty_abuse.features import FeatureStore
from loyalty_abuse.schema import EventEnvelope, EventType, FrictionAction


def test_clean_redeem_allows():
    store = FeatureStore()
    store.observe(
        EventEnvelope(
            event_id="s1",
            tenant_id="t",
            ts="2026-08-01T00:00:00Z",
            type=EventType.signup,
            account_id="a",
            session_id="s",
            device_id="d",
            ip="1.1.1.1",
            payload={},
        )
    )
    d = evaluate(
        EventEnvelope(
            event_id="r1",
            tenant_id="t",
            ts="2026-08-04T12:00:00Z",
            type=EventType.redeem,
            account_id="a",
            session_id="s",
            device_id="d",
            ip="1.1.1.1",
            payload={"reward_id": "r", "points": 10, "offer_ids": ["one"], "channel": "app"},
        ),
        store,
    )
    assert d.friction == FrictionAction.allow
    assert d.score < 25
    assert isinstance(d.reasons, list)


def test_ato_forces_hard_floor():
    store = FeatureStore()
    base = dict(tenant_id="t", account_id="a1", session_id="s", ip="1.1.1.1", payload={})
    store.observe(EventEnvelope(event_id="s1", ts="2026-08-04T10:00:00Z", type=EventType.signup, device_id="old", **base))
    store.observe(
        EventEnvelope(
            event_id="l1",
            ts="2026-08-04T12:00:00Z",
            type=EventType.login,
            device_id="new",
            email=None,
            phone=None,
            payment_instrument_hash=None,
            tenant_id="t",
            account_id="a1",
            session_id="s",
            ip="9.9.9.9",
            payload={"success": True, "new_device": True, "geo": "XX"},
        )
    )
    store.observe(
        EventEnvelope(
            event_id="p1",
            ts="2026-08-04T12:01:00Z",
            type=EventType.profile_update,
            device_id="new",
            tenant_id="t",
            account_id="a1",
            session_id="s",
            ip="9.9.9.9",
            payload={"fields_changed": ["email"]},
        )
    )
    d = evaluate(
        EventEnvelope(
            event_id="r1",
            ts="2026-08-04T12:02:00Z",
            type=EventType.redeem,
            device_id="new",
            tenant_id="t",
            account_id="a1",
            session_id="s",
            ip="9.9.9.9",
            payload={"reward_id": "r", "points": 50, "offer_ids": [], "channel": "app"},
        ),
        store,
    )
    assert d.friction in {FrictionAction.hard_challenge, FrictionAction.block}
    assert "ato.login_profile_redeem_chain" in d.reasons
```

Also add `tests/fixtures/golden_tiers.json` with five objects `{name, events[], expected_friction, expected_reason_substring}` (one per tier) and a parametrized test that replays `events` through `FeatureStore` + `evaluate` on the last event and asserts friction + reason substring.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_evaluate.py -v`
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

```python
# src/loyalty_abuse/typologies/base.py
from __future__ import annotations
from typing import Any, Callable
from loyalty_abuse.schema import TypologyResult

Scorer = Callable[[dict[str, Any]], TypologyResult]
```

```python
# src/loyalty_abuse/typologies/multi_account.py
from __future__ import annotations
from typing import Any
from loyalty_abuse.schema import TypologyResult

def score(snapshot: dict[str, Any]) -> TypologyResult:
    points, reasons = 0, []
    if int(snapshot.get("accounts_on_device_24h") or 0) >= 3:
        points += 30
        reasons.append("multi_acct.shared_device_cluster")
    if snapshot.get("email_alias_burst"):
        points += 15
        reasons.append("multi_acct.email_alias_burst")
    return TypologyResult(id="multi_account", points=points, reasons=reasons)
```

```python
# src/loyalty_abuse/typologies/referral_self_deal.py
from __future__ import annotations
from typing import Any
from loyalty_abuse.schema import TypologyResult

def score(snapshot: dict[str, Any]) -> TypologyResult:
    points, reasons = 0, []
    if snapshot.get("referral_shared_device"):
        points += 30
        reasons.append("referral.shared_device")
    if snapshot.get("referral_shared_payment"):
        points += 20
        reasons.append("referral.shared_payment")
    return TypologyResult(id="referral_self_deal", points=points, reasons=reasons)
```

```python
# src/loyalty_abuse/typologies/promo_stack.py
from __future__ import annotations
from typing import Any
from loyalty_abuse.schema import TypologyResult

def score(snapshot: dict[str, Any]) -> TypologyResult:
    points, reasons = 0, []
    if int(snapshot.get("stack_depth") or 0) >= 3:
        points += 20
        reasons.append("promo.stack_depth")
    if float(snapshot.get("discount_depth") or 0) >= 50:
        points += 15
        reasons.append("promo.discount_depth")
    return TypologyResult(id="promo_stack", points=points, reasons=reasons)
```

```python
# src/loyalty_abuse/typologies/bot_redeem.py
from __future__ import annotations
from typing import Any
from loyalty_abuse.schema import TypologyResult

def score(snapshot: dict[str, Any]) -> TypologyResult:
    points, reasons = 0, []
    if int(snapshot.get("redeem_count_5m") or 0) >= 10:
        points += 30
        reasons.append("bot.redeem_velocity")
    if int(snapshot.get("signup_count_5m") or 0) >= 8:
        points += 20
        reasons.append("bot.signup_velocity")
    return TypologyResult(id="bot_redeem", points=points, reasons=reasons)
```

```python
# src/loyalty_abuse/typologies/code_leak.py
from __future__ import annotations
from typing import Any
from loyalty_abuse.schema import TypologyResult

def score(snapshot: dict[str, Any]) -> TypologyResult:
    points, reasons = 0, []
    if int(snapshot.get("code_unique_users_24h") or 0) >= 25:
        points += 25
        reasons.append("code.unique_user_spike")
    return TypologyResult(id="code_leak", points=points, reasons=reasons)
```

```python
# src/loyalty_abuse/typologies/ato_redeem.py
from __future__ import annotations
from typing import Any
from loyalty_abuse.schema import TypologyResult

def score(snapshot: dict[str, Any]) -> TypologyResult:
    points, reasons = 0, []
    if snapshot.get("ato_chain"):
        points += 40
        reasons.append("ato.login_profile_redeem_chain")
    return TypologyResult(id="ato_redeem", points=points, reasons=reasons)
```

```python
# src/loyalty_abuse/typologies/__init__.py
from loyalty_abuse.typologies import (
    ato_redeem,
    bot_redeem,
    code_leak,
    multi_account,
    promo_stack,
    referral_self_deal,
)

ALL_SCORERS = [
    multi_account.score,
    referral_self_deal.score,
    promo_stack.score,
    bot_redeem.score,
    code_leak.score,
    ato_redeem.score,
]
```

```python
# src/loyalty_abuse/score.py
from __future__ import annotations

import uuid

from loyalty_abuse.features import FeatureStore
from loyalty_abuse.policy import FrictionPolicy
from loyalty_abuse.schema import Decision, EventEnvelope
from loyalty_abuse.typologies import ALL_SCORERS


def evaluate(
    event: EventEnvelope,
    store: FeatureStore,
    policy: FrictionPolicy | None = None,
) -> Decision:
    policy = policy or FrictionPolicy()
    store.observe(event)
    snap = store.snapshot(event)
    results = [s(snap) for s in ALL_SCORERS]
    results = [r for r in results if r.points > 0]
    score = min(100, sum(r.points for r in results))
    reasons = [r for tr in results for r in tr.reasons]
    friction = policy.action_for(score, force_hard_floor=bool(snap.get("force_hard_floor")))
    return Decision(
        decision_id="dec_" + uuid.uuid4().hex,
        event_id=event.event_id,
        score=score,
        friction=friction,
        reasons=reasons,
        typology_breakdown=results,
        features_snapshot=snap,
        policy_version=policy.version,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_evaluate.py tests/test_features.py tests/test_policy.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/loyalty_abuse/typologies src/loyalty_abuse/score.py tests/test_evaluate.py tests/fixtures/golden_tiers.json src/loyalty_abuse/__init__.py
git commit -m "feat: add typology scorers and evaluate()"
```

---

### Task 5: JSON contracts

**Files:**
- Create: `contracts/event-envelope.schema.json`
- Create: `contracts/evaluate-request.schema.json`
- Create: `contracts/decision.schema.json`
- Create: `tests/test_contracts.py`

**Interfaces:**
- Consumes: pydantic models
- Produces: draft-2020-12 JSON Schema files matching model fields; test loads schemas with stdlib `json` and validates example payloads via `jsonschema` **or** round-trip: `Decision.model_validate` on examples embedded in test (prefer pydantic round-trip to avoid new dep — **do not add jsonschema**; assert `model_json_schema()` keys ⊇ required fields and dump example files match models)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_contracts.py
import json
from pathlib import Path
from loyalty_abuse.schema import Decision, EventEnvelope

ROOT = Path(__file__).resolve().parents[1] / "contracts"


def test_contract_files_exist():
    for name in ("event-envelope.schema.json", "evaluate-request.schema.json", "decision.schema.json"):
        assert (ROOT / name).is_file()


def test_event_schema_lists_required():
    schema = json.loads((ROOT / "event-envelope.schema.json").read_text())
    for key in ("event_id", "tenant_id", "ts", "type", "account_id", "device_id", "ip"):
        assert key in schema.get("required", []) or key in schema.get("properties", {})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_contracts.py -v`
Expected: FAIL (missing files)

- [ ] **Step 3: Write minimal implementation**

Write the three JSON schema files (hand-authored, aligned to pydantic fields). `evaluate-request.schema.json` allows either `{ "event_id": "..." }` or `{ "event": { ...EventEnvelope } }` plus optional `evaluate` bool for events POST.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_contracts.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add contracts tests/test_contracts.py
git commit -m "feat: add stable JSON contracts for event and decision"
```

---

### Task 6: SQLite persistence + FastAPI adapter (fail-closed audit)

**Files:**
- Create: `src/loyalty_abuse_api/__init__.py`
- Create: `src/loyalty_abuse_api/db.py`
- Create: `src/loyalty_abuse_api/app.py`
- Create: `tests/test_api.py`

**Interfaces:**
- Consumes: `evaluate`, `EventEnvelope`, `Decision`, `FeatureStore` (process-global or app.state)
- Produces:
  - `POST /v1/events` body: EventEnvelope + optional `evaluate: bool` → `{event_id}` or Decision
  - `POST /v1/evaluate` body: `{event_id}` or `{event: EventEnvelope}` → Decision
  - `GET /v1/decisions/{decision_id}` → Decision JSON
  - Persist event before/with evaluate; **insert decision row before return**; if insert fails, raise HTTP 503

- [ ] **Step 1: Write the failing test**

```python
# tests/test_api.py
from fastapi.testclient import TestClient
from loyalty_abuse_api.app import create_app


def test_evaluate_persists_before_200(tmp_path):
    app = create_app(db_path=tmp_path / "t.db")
    client = TestClient(app)
    ev = {
        "event_id": "evt_api_1",
        "tenant_id": "t",
        "ts": "2026-08-04T12:00:00Z",
        "type": "signup",
        "account_id": "a",
        "session_id": "s",
        "device_id": "d",
        "ip": "1.1.1.1",
        "payload": {},
    }
    r = client.post("/v1/events", json={**ev, "evaluate": True})
    assert r.status_code == 200
    body = r.json()
    assert body["friction"] in {"allow", "throttle", "soft_challenge", "hard_challenge", "block"}
    d = client.get(f"/v1/decisions/{body['decision_id']}")
    assert d.status_code == 200
    assert d.json()["event_id"] == "evt_api_1"


def test_audit_failure_returns_503(tmp_path, monkeypatch):
    app = create_app(db_path=tmp_path / "t.db")
    client = TestClient(app)

    def boom(*_a, **_k):
        raise RuntimeError("disk full")

    monkeypatch.setattr(app.state.db, "save_decision", boom)
    ev = {
        "event_id": "evt_api_2",
        "tenant_id": "t",
        "ts": "2026-08-04T12:00:00Z",
        "type": "signup",
        "account_id": "a",
        "session_id": "s",
        "device_id": "d",
        "ip": "1.1.1.1",
        "payload": {},
    }
    r = client.post("/v1/evaluate", json={"event": ev})
    assert r.status_code == 503
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_api.py -v`
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

`db.py`: SQLite schema `events(event_id PK, tenant_id, ts, body_json)` and `decisions(decision_id PK, event_id, body_json, created_at)`.
`app.py`: `create_app(db_path)` wires store + db; on evaluate path: load/observe historical events for tenant into `FeatureStore` (or observe each ingest into store kept in app.state), call `evaluate`, `db.save_decision`, then return. Catch DB errors → 503.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_api.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/loyalty_abuse_api tests/test_api.py
git commit -m "feat: add FastAPI adapter with fail-closed decision audit"
```

---

### Task 7: Analytics summary + demo seed

**Files:**
- Create: `src/loyalty_abuse_api/analytics.py`
- Modify: `src/loyalty_abuse_api/app.py` — add `GET /v1/analytics/summary`
- Create: `scripts/seed_demo.py`
- Create: `tests/test_analytics.py`

**Interfaces:**
- Consumes: decision rows from SQLite
- Produces: summary `{friction_counts, score_histogram, top_reasons, typology_rates, decision_count}`; seed script inserts clean + six Accertify pattern scenarios via HTTP or db

- [ ] **Step 1: Write the failing test**

```python
# tests/test_analytics.py
from fastapi.testclient import TestClient
from loyalty_abuse_api.app import create_app


def test_summary_empty(tmp_path):
    client = TestClient(create_app(db_path=tmp_path / "t.db"))
    r = client.get("/v1/analytics/summary")
    assert r.status_code == 200
    assert r.json()["decision_count"] == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_analytics.py -v`
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

Implement `build_summary(decisions: list[dict]) -> dict` and route. `scripts/seed_demo.py` uses httpx against `BASE_URL` (default `http://127.0.0.1:8080`) to post pattern sequences labeled in comments (multi_account, referral_self_deal, promo_stack, bot_redeem, code_leak, ato_redeem) plus clean users.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_analytics.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/loyalty_abuse_api/analytics.py src/loyalty_abuse_api/app.py scripts/seed_demo.py tests/test_analytics.py
git commit -m "feat: add analytics summary and demo seed script"
```

---

### Task 8: Dashboard + offline eval script

**Files:**
- Create: `static/index.html`
- Modify: `src/loyalty_abuse_api/app.py` — mount `StaticFiles` at `/` or `/dashboard`
- Create: `notebooks/offline_eval.py`
- Create: `tests/test_offline_eval.py`

**Interfaces:**
- Dashboard fetches `GET /v1/analytics/summary` and renders friction mix, top reasons, typology rates (plain HTML/JS, no build step).
- `notebooks/offline_eval.py` CLI: `--db path` → prints friction distribution, reason coverage, and threshold sweep table (recompute friction bands 20/40/60/80 vs stored scores). Exit 0 always when db readable.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_offline_eval.py
from notebooks.offline_eval import summarize_decisions


def test_summarize_decisions_counts():
    rows = [
        {"score": 10, "friction": "allow", "reasons": [], "typology_breakdown": []},
        {"score": 90, "friction": "block", "reasons": ["bot.redeem_velocity"], "typology_breakdown": [{"id": "bot_redeem"}]},
    ]
    s = summarize_decisions(rows)
    assert s["decision_count"] == 2
    assert s["friction_counts"]["block"] == 1
```

(If import path is awkward, put `summarize_decisions` in `loyalty_abuse_api/analytics.py` and have the notebook script call it — prefer that DRY path.)

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_offline_eval.py -v`
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

Reuse analytics helpers. Static page: fetch summary, render three simple tables. Wire `app.mount("/", StaticFiles(directory="static", html=True), name="static")` **after** API routes so `/v1/*` wins.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_offline_eval.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add static/index.html notebooks/offline_eval.py src/loyalty_abuse_api/app.py src/loyalty_abuse_api/analytics.py tests/test_offline_eval.py
git commit -m "feat: add analytics dashboard and offline eval script"
```

---

### Task 9: Docker compose, README, adapters stub

**Files:**
- Create: `Dockerfile`
- Create: `docker-compose.yml`
- Create: `adapters/tarka/README.md`
- Modify: `README.md` — full quickstart (library + HTTP + docker + seed + eval)
- Create: `tests/test_library_no_fastapi_import.py`

**Interfaces:**
- Consumes: API app module path `loyalty_abuse_api.app:create_app` / `app`
- Produces: runnable compose on port 8080; README documents in-process `evaluate()` and HTTP; Tarka adapter README states “optional, not shipped in v1”

- [ ] **Step 1: Write the failing test**

```python
# tests/test_library_no_fastapi_import.py
import ast
from pathlib import Path

def test_core_does_not_import_fastapi():
    root = Path("src/loyalty_abuse")
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for n in node.names:
                    assert not n.name.startswith("fastapi")
                    assert n.name != "uvicorn"
            if isinstance(node, ast.ImportFrom) and node.module:
                assert not node.module.startswith("fastapi")
                assert node.module != "uvicorn"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_library_no_fastapi_import.py -v`
Expected: may PASS already if clean — if PASS, keep test as regression gate

- [ ] **Step 3: Write Dockerfile + compose + README**

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
COPY static ./static
COPY contracts ./contracts
RUN pip install --no-cache-dir .
ENV LOYALTY_ABUSE_DB=/data/loyalty.db
EXPOSE 8080
CMD ["uvicorn", "loyalty_abuse_api.app:app", "--host", "0.0.0.0", "--port", "8080"]
```

Expose module-level `app = create_app()` in `app.py` reading `LOYALTY_ABUSE_DB`.

`docker-compose.yml`: service `api` build `.`, ports `8080:8080`, volume for `/data`.

`adapters/tarka/README.md`: explain mapping EventEnvelope ↔ host evaluate payload and friction → host actions; no code.

- [ ] **Step 4: Run full suite**

Run: `pytest -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add Dockerfile docker-compose.yml README.md adapters/tarka/README.md tests/test_library_no_fastapi_import.py src/loyalty_abuse_api/app.py
git commit -m "feat: add docker compose standalone run and host-adapter notes"
```

---

## Spec coverage checklist

| Spec requirement | Task |
|---|---|
| Standalone-first library | 1, 4, 9 |
| No Tarka dependency in core | 9 (AST gate); adapter stub only |
| Event types + envelope | 1, 5 |
| Feature families | 3 |
| Six typologies + reason codes | 4 |
| Explainable Decision | 1, 4 |
| Friction ladder + hard floor | 2, 4 |
| No review action | 1, 2 |
| HTTP API | 6 |
| Fail-closed audit | 6 |
| Analytics summary | 7 |
| Demo seed (six patterns) | 7 |
| Dashboard | 8 |
| Offline eval | 8 |
| Docker compose | 9 |
| JSON contracts | 5 |
| Golden friction tiers | 4 |

## Deferred (not in this plan)

- Bounded ML score delta
- Redis / Neo4j
- Implemented `adapters/tarka/` Python mapper (README only)
