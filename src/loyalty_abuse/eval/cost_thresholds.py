"""Cost-optimal friction band selection on a locked labeled validation set.

Objective (labeled, not probabilistic):
  sum_i C_fn * liability_i * label_i * miss_fraction[friction_i] + C_fp[friction_i]

Friction for a candidate band is max(score-band action, floor_min) where
floor_min is the absolute floor raise observed from full evaluate() (soft/hard
floors). Score-only selection previously ignored ATO/floor production behavior.
"""

from __future__ import annotations

import itertools
import random
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Sequence

from loyalty_abuse.eval.adversarial import GENERATORS, N_PER_SLICE
from loyalty_abuse.features import FeatureStore
from loyalty_abuse.floors import FRICTION_ORDER, max_friction
from loyalty_abuse.policy import FrictionPolicy
from loyalty_abuse.schema import FrictionAction
from loyalty_abuse.score import evaluate

Row = Mapping[str, Any]

DEFAULT_BASELINE = {
    "allow_max": 24,
    "throttle_max": 44,
    "soft_max": 64,
    "hard_max": 84,
}

# Coarse grid around baseline. allow_max stays at/above baseline so shared-device
# allow goldens and household UX are not crushed by $C_fp << liability*C_fn.
# Upper knees may tighten for high-liability abuse (unit-test / val selection).
DEFAULT_KNEE_GRID: dict[str, tuple[int, ...]] = {
    "allow_max": (24, 28),
    "throttle_max": (28, 32, 36, 40, 44, 50),
    "soft_max": (48, 52, 56, 60, 64, 70),
    "hard_max": (68, 72, 76, 80, 84, 90),
}

_SLICE_ABUSE: dict[str, bool] = {
    "household_fp": False,
    "device_rotation": True,
    "slow_multi_acct": True,
    "sequential_promo": True,
    "ato_known_device": True,
    "graph_payment_ring": True,
}

_MONEY_KEYS = ("points_liability_usd", "discount_usd", "referral_bonus_usd")
_DEFAULT_LIABILITY_ABUSE = 25.0
_DEFAULT_LIABILITY_LEGIT = 5.0


def _friction_with_floors(
    score: int,
    bands: Mapping[str, int],
    floor_min: str | None,
) -> FrictionAction:
    policy = FrictionPolicy(
        allow_max=int(bands["allow_max"]),
        throttle_max=int(bands["throttle_max"]),
        soft_max=int(bands["soft_max"]),
        hard_max=int(bands["hard_max"]),
    )
    friction = policy.action_for(int(score))
    if floor_min:
        friction = max_friction(friction, FrictionAction(floor_min))
    return friction


def total_labeled_cost(
    rows: Sequence[Row],
    bands: Mapping[str, int],
    cost: Mapping[str, Any],
) -> float:
    """Sum labeled loss+insult under candidate bands + evaluate() floor mins."""
    c_fn = float(cost["C_fn_per_usd"])
    c_fp = cost["C_fp"]
    miss = cost["miss_fraction"]
    total = 0.0
    for row in rows:
        friction = _friction_with_floors(
            int(row["score"]), bands, row.get("floor_min")  # type: ignore[arg-type]
        )
        key = friction.value
        label = 1.0 if row["label_abuse"] else 0.0
        total += c_fn * float(row["liability_usd"]) * label * float(miss[key])
        total += float(c_fp[key])
    return total


def _valid_bands(bands: Mapping[str, int]) -> bool:
    return (
        bands["allow_max"]
        < bands["throttle_max"]
        < bands["soft_max"]
        < bands["hard_max"]
        < 100
    )


def iter_candidate_bands(
    grid: Mapping[str, Sequence[int]] | None = None,
    *,
    baseline: Mapping[str, int] | None = None,
) -> Iterable[dict[str, int]]:
    g = {k: list(v) for k, v in (grid or DEFAULT_KNEE_GRID).items()}
    base = dict(baseline or DEFAULT_BASELINE)
    for k, v in base.items():
        vals = g.setdefault(k, [])
        if v not in vals:
            vals.append(v)
            vals.sort()
    keys = ("allow_max", "throttle_max", "soft_max", "hard_max")
    for combo in itertools.product(*(g[k] for k in keys)):
        bands = dict(zip(keys, combo))
        if _valid_bands(bands):
            yield bands


def select_bands(
    rows: Sequence[Row],
    cost: Mapping[str, Any],
    *,
    baseline: Mapping[str, int] | None = None,
    grid: Mapping[str, Sequence[int]] | None = None,
) -> dict[str, int]:
    """Return bands minimizing total_labeled_cost on ``rows``.

    Ties break toward the baseline (if present) then lexicographically lower knees.
    """
    if not rows:
        raise ValueError("rows must be non-empty")
    base = dict(baseline or DEFAULT_BASELINE)
    best: dict[str, int] | None = None
    best_cost = float("inf")
    for bands in iter_candidate_bands(grid, baseline=base):
        c = total_labeled_cost(rows, bands, cost)
        if c < best_cost - 1e-12:
            best_cost = c
            best = bands
            continue
        if abs(c - best_cost) <= 1e-12 and best is not None:
            if bands == base:
                best = bands
            elif best != base and tuple(bands[k] for k in bands) < tuple(
                best[k] for k in best
            ):
                best = bands
    assert best is not None
    return best


def liability_for_payload(payload: Mapping[str, Any] | None, *, abuse: bool) -> float:
    """Sum money keys from payload; fall back to synthetic defaults if absent."""
    total = 0.0
    for key in _MONEY_KEYS:
        raw = (payload or {}).get(key)
        if raw is None:
            continue
        total += float(raw)
    if total > 0.0:
        return total
    return _DEFAULT_LIABILITY_ABUSE if abuse else _DEFAULT_LIABILITY_LEGIT


def _decide_journey(events: list):
    store = FeatureStore()
    for e in events[:-1]:
        store.observe(e)
    return evaluate(events[-1], store)


def _floor_min_from_decision(d) -> str | None:
    """Absolute friction floor implied by soft/hard floors (above score band)."""
    band = str((d.features_snapshot or {}).get("band_friction") or "allow")
    final = d.friction.value
    if FRICTION_ORDER.index(FrictionAction(final)) > FRICTION_ORDER.index(
        FrictionAction(band)
    ):
        return final
    return None


def build_adversarial_labeled_rows(
    seed: int,
    *,
    n_per_slice: int = N_PER_SLICE,
) -> list[dict[str, Any]]:
    """Score adversarial journeys; label household as legit, other slices as abuse."""
    rng = random.Random(seed)
    base = datetime(2026, 8, 5, 12, 0, 0, tzinfo=timezone.utc)
    rows: list[dict[str, Any]] = []
    for name, gen in GENERATORS.items():
        abuse = _SLICE_ABUSE[name]
        for j in range(n_per_slice):
            jr = random.Random(rng.randint(0, 2**31 - 1))
            events = gen(j, jr, base)
            d = _decide_journey(events)
            rows.append(
                {
                    "score": int(d.score),
                    "friction": d.friction.value,
                    "band_friction": (d.features_snapshot or {}).get("band_friction"),
                    "floor_min": _floor_min_from_decision(d),
                    "p_abuse": d.p_abuse,
                    "liability_usd": liability_for_payload(
                        events[-1].payload, abuse=abuse
                    ),
                    "label_abuse": abuse,
                    "slice": name,
                    "source": "adversarial",
                }
            )
    return rows
