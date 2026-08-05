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
| `POST /v1/evaluate` | Score by `event_id` or inline `event` |
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

**Honest B+ proof** is the adversarial suite (not the large synth run):

```bash
python scripts/adversarial_eval.py --seed 42 --out artifacts/adversarial_v1_2.json
```

Exit code 0 only when all slice bounds pass (household FP allow-rate, device-rotation / slow-multi / sequential-promo / known-device ATO catch-rates). See `src/loyalty_abuse/eval/adversarial.py` for published bounds.

**Honest B+ claim:** Catch slices stack multiple typologies under `weighted_sum` (single typology capped ~28, below soft_challenge at 45). Anti-vanity forbids velocity hard_floor padding without pattern reason families. `ato_known_device` may elevate via `ato_chain` hybrid hard_floor while confidence still contributes to score.

The synthetic 500k eval (`scripts/synth_eval.py`) is **regression-only** — it must not be cited as the B+ grade claim.

After decisions are persisted:

```bash
python notebooks/offline_eval.py --db loyalty_abuse.db
```

Prints stored friction distribution, reason coverage, and a threshold sweep (24/44/64/84 vs 20/40/60/80).

## Tests

```bash
pytest -v
```

## Host adapters

Optional Tarka integration notes (no code in v1): [`adapters/tarka/README.md`](adapters/tarka/README.md).
