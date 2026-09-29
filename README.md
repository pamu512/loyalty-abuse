# loyalty-abuse

Standalone loyalty abuse scorer with explainable friction: detect and interrupt promotion abuse across the guest journey with an explainable score and tiered friction up to block.

See [docs/superpowers/specs/2026-08-04-loyalty-abuse-design.md](docs/superpowers/specs/2026-08-04-loyalty-abuse-design.md) for the full design.

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Loyalty economics multi-gate

Program LTV / loyalty-ratio gates (`dispatch` / `redeem` / `order`) live here — not in Tarka.

- Engine: [`src/loyalty_abuse/multi_gate.py`](src/loyalty_abuse/multi_gate.py) (`evaluate_loyalty_economics`)
- Warehouse pack: [`src/loyalty_abuse/warehouse.py`](src/loyalty_abuse/warehouse.py)
- Config example: [`contracts/loyalty_program_config.example.json`](contracts/loyalty_program_config.example.json)
- Prerequisites: [`docs/guides/loyalty-economics-prerequisites.md`](docs/guides/loyalty-economics-prerequisites.md)
- Design: [`docs/superpowers/specs/2026-08-06-loyalty-economics-multi-gate-design.md`](docs/superpowers/specs/2026-08-06-loyalty-economics-multi-gate-design.md)

```bash
.venv/bin/python -m pytest tests/test_multi_gate.py -q
.venv/bin/python scripts/loyalty_economics_feed_smoke.py
```

Note: [`src/loyalty_abuse/economics.py`](src/loyalty_abuse/economics.py) is decision liability / insult USD — different module.

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
| `GET /v1/analytics/summary` | Friction mix, top reasons, typology rates, ops metrics |
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

**Privacy:** Letter-grade maturity ratings are private — see [`docs/compliance/RATINGS_PRIVATE.md`](docs/compliance/RATINGS_PRIVATE.md). Public docs describe gates and capabilities only.

### Primary gate (adversarial suite)

Adversarial suite on current policy (`policy_version` in artifact):

```bash
PYTHONPATH=src python3 scripts/adversarial_eval.py --seed 42 --out artifacts/adversarial_v3_0.json
PYTHONPATH=src python3 -c "from loyalty_abuse.eval.external_holdout import run_external_holdout; print(run_external_holdout()['gates_pass'])"
```

Exit code 0 only when all slice bounds pass (household FP allow-rate ≥ 0.85 and block-rate ≤ 0.5; device-rotation / slow-multi / sequential-promo / known-device ATO catch-rates at soft_challenge+). See `src/loyalty_abuse/eval/adversarial.py` for published bounds.

**Catch-power:** Score blend includes published interaction terms (`ix.*` in breakdown). Soft floors (`floor.soft.*`) may raise friction without raising score — a lone typology can sit below the soft band while friction reaches `soft_challenge+` via floor predicates. Adversarial gates require pattern slices to catch honestly (typology, interaction, or soft-floor attribution; no redeem-velocity hard_floor vanity; combined pattern block-rate ≤ 0.5). Frozen external holdout: `tests/fixtures/external_journeys.json`.

The synthetic 500k eval (`scripts/synth_eval.py`) is **regression-only** — it must not be cited as a readiness claim.

### In-repo technical bar (Phase 2)

| Artifact | Command | Published result |
|---|---|---|
| Cost-optimal knees | `PYTHONPATH=src python3 scripts/select_thresholds.py --val-seed 7 --report-seed 42` | Val cost 2975→2275; report cost 4371→3514; bands `{24,28,48,68}` |
| Graph ablation | `PYTHONPATH=src python3 scripts/ablation_graph.py --seed 42` | Household allow 0pp drop; catch/cost unchanged on this holdout |
| Platt + ECE/Brier | `PYTHONPATH=src python3 scripts/fit_calibration.py --fit-seed 7 --report-seed 42` | Synth score-path ECE ~0.14 (ceiling **0.15**); production outcome ECE must be ≤**0.05** via `fit_calibration_from_labels.py` |
| Shadow dry-run | `PYTHONPATH=src python3 scripts/shadow_dry_run.py --n 200 --days 14` | Pipeline exists; synthetic precision/recall/insult-proxy only |

Summaries: [`docs/superpowers/artifacts/`](docs/superpowers/artifacts/). Raw JSON under `artifacts/` (gitignored).

Dollar-weighted threshold selection, graph ablation, calibrated `p_abuse`, and shadow logging are wired in-repo. Graph ablation shows no incremental catch on this synthetic holdout — graph value remains unproven until denser tenant graphs or production labels.

**Live shadow readiness** additionally requires real later-confirmed outcome labels and **≥4 weeks** of shadow vs host action. Synthetic dry-runs and in-repo 28-day sims prove pipeline wiring only. Fail-closed gate: `python3 scripts/assert_live_shadow_readiness.py`.

### Device-intel + ops path (Phase 3 — in-repo)

Incognia adapter (fixture + live-gated), challenge outcome ingest, consortium no-op stub, continual drift re-eval, and ops metrics on `GET /v1/analytics/summary` are shipped.

```bash
PYTHONPATH=src python3 scripts/drift_reeval.py --seed 42 --out artifacts/drift_reeval.json
```

Exit 1 if any adversarial slice fails its bound.

**Live device-intel** needs live Incognia credentials, real challenge labels, and weeks of ops — do not treat fixtures or dry-runs as live proof. See `docs/compliance/incognia-live.status`.

### Phase 4 — Catch-power + shadow/label loop (in-repo)

**Catch-power:** Published interaction terms (`ix.*`) on the score blend plus soft-floor predicates (`floor.soft.*`) that raise friction without raising score. `evaluate()` stores `band_friction` in `features_snapshot` (score-band action before floors) for honest ops attribution.

**Shadow/label loop:** Outcome labels join decisions; retrain gate checks held-out ECE; four-week playbook at [`docs/superpowers/playbooks/2026-08-05-shadow-four-week.md`](docs/superpowers/playbooks/2026-08-05-shadow-four-week.md); synthetic 28-day sim:

```bash
PYTHONPATH=src python3 scripts/shadow_four_week_sim.py --seed 42 --out artifacts/shadow_four_week_sim.json
```

Ops metrics on `GET /v1/analytics/summary` include `floor_raised_count` / `floor_raised_rate` (decisions where soft-floor reasons fired or final friction exceeds score-band friction).

Phase 4 closes the in-repo path (catch-power, shadow logging, label join, retrain gate, playbook, sim). Live production readiness still requires **≥4 weeks** of live shadow vs host action and real outcome labels.

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

- Incognia: [`adapters/incognia/README.md`](adapters/incognia/README.md)
- Consortium: fail-closed stub — typed `not_configured` / `missing_feed` (never silent `{}`). Live consortium is not shipped. [`adapters/consortium/`](adapters/consortium/)
- Tarka notes (no code in v1): [`adapters/tarka/README.md`](adapters/tarka/README.md)
