# loyalty-abuse

Standalone QSR loyalty abuse scorer with explainable friction: detect and interrupt promotion abuse across the guest journey with an explainable score and tiered friction up to block.

See [docs/superpowers/specs/2026-08-04-qsr-loyalty-abuse-design.md](docs/superpowers/specs/2026-08-04-qsr-loyalty-abuse-design.md) for the full design.

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## In-process library

Score an event without HTTP — persistence and audit are your responsibility:

```python
from loyalty_abuse import evaluate
from loyalty_abuse.features import FeatureStore
from loyalty_abuse.schema import EventEnvelope, EventType

store = FeatureStore()
store.observe(EventEnvelope(
    event_id="s1", tenant_id="demo", ts="2026-08-01T00:00:00Z",
    type=EventType.signup, account_id="a", session_id="s",
    device_id="d", ip="1.1.1.1", payload={},
))
decision = evaluate(EventEnvelope(
    event_id="r1", tenant_id="demo", ts="2026-08-04T12:00:00Z",
    type=EventType.redeem, account_id="a", session_id="s",
    device_id="d", ip="1.1.1.1",
    payload={"reward_id": "r", "points": 10, "offer_ids": ["one"], "channel": "app"},
), store)
print(decision.score, decision.friction, decision.reasons)
```

JSON contracts: [`contracts/`](contracts/).

## HTTP API (local)

```bash
uvicorn loyalty_abuse_api.app:app --host 0.0.0.0 --port 8080
```

Set `LOYALTY_ABUSE_DB` to override the SQLite path (default `loyalty_abuse.db`).

| Endpoint | Purpose |
|---|---|
| `POST /v1/events` | Ingest `EventEnvelope`; optional `"evaluate": true` |
| `POST /v1/evaluate` | Score by `event_id` or inline `event` (enforcing) |
| `POST /v1/shadow/evaluate` | Shadow score; optional `host_friction`; logs recommended vs host |
| `GET /v1/decisions/{id}` | Fetch audited decision |
| `GET /v1/analytics/summary` | Friction mix, top reasons, typology rates |
| `/` | Static analytics dashboard |

## Docker Compose

```bash
docker compose up --build
```

API and dashboard at [http://localhost:8080](http://localhost:8080). SQLite persists in the `loyalty_data` volume at `/data/loyalty.db`.

## Demo seed

With the API running:

```bash
python scripts/seed_demo.py
```

Seeds six abuse patterns (multi-account, promo stack, referral self-deal, bot redeem, code leak, ATO redeem) plus a clean baseline via `POST /v1/events`.

## Offline evaluation

**Grade claims** (see [program spec](docs/superpowers/specs/2026-08-05-a-plus-plus-program-design.md)) require the artifacts below — not synth gate polish.

### Primary gate (B+ floor, still required)

Adversarial suite on `friction_v2_0` (`policy_version` in artifact):

```bash
PYTHONPATH=src python3 scripts/adversarial_eval.py --seed 42 --out artifacts/adversarial_v2_0.json
```

Exit code 0 only when all slice bounds pass (household FP allow-rate, device-rotation / slow-multi / sequential-promo / known-device ATO catch-rates). See `src/loyalty_abuse/eval/adversarial.py` for published bounds.

The synthetic 500k eval (`scripts/synth_eval.py`) is **regression-only** — it must not be cited as a grade claim.

### Standalone A bar (Phase 2 — in-repo)

| Artifact | Command | Published result |
|---|---|---|
| Cost-optimal knees | `PYTHONPATH=src python3 scripts/select_thresholds.py --val-seed 7 --report-seed 42` | Val cost 2975→2275; report cost 4371→3514; bands `{24,28,48,68}` |
| Graph ablation | `PYTHONPATH=src python3 scripts/ablation_graph.py --seed 42` | Household allow 0pp drop; catch/cost unchanged on this holdout |
| Platt + ECE/Brier | `PYTHONPATH=src python3 scripts/fit_calibration.py --fit-seed 7 --report-seed 42` | Held-out seed 42 ECE ≈ 0; labels: synthetic red-team 2026-08-05 |
| Shadow dry-run | `PYTHONPATH=src python3 scripts/shadow_dry_run.py --n 200 --days 14` | Pipeline exists; synthetic precision/recall/insult-proxy only |

Summaries: [`docs/superpowers/artifacts/`](docs/superpowers/artifacts/). Raw JSON under `artifacts/` (gitignored).

**Honest standalone A claim:** Dollar-weighted threshold selection, graph ablation report, calibrated `p_abuse` with held-out ECE, and shadow logging are all wired and published. Graph ablation shows no incremental catch on this synthetic holdout — graph value remains unproven until denser tenant graphs or production labels.

**Not production A+:** Live A+ additionally requires real later-confirmed outcome labels and **≥4 weeks** of shadow vs host action. The synthetic dry-run (`artifacts/shadow_dry_run.json`: precision 1.0, recall 0.4, insult_proxy 0.0) proves the reporter path only — do not claim live A+ from it.

After decisions are persisted:

```bash
python notebooks/offline_eval.py --db loyalty_abuse.db
```

Prints stored friction distribution, reason coverage, and a threshold sweep (baseline `{24,44,64,84}` vs selected `{24,28,48,68}`).

## Tests

```bash
pytest -v
```

## Host adapters

Optional Tarka integration notes (no code in v1): [`adapters/tarka/README.md`](adapters/tarka/README.md).
