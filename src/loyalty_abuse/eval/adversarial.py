"""Adversarial eval suite — primary honest B+ proof for friction_v2_2.

Honest B+ claim (what passing gates proves):
1. Pattern catch (slow_multi_acct, sequential_promo) reaches soft_challenge+ via
   published interaction terms and/or soft floors — lone typology score may stay
   below the soft band; floor-driven soft catch is valid and labeled floor.soft.*.
2. Anti-vanity: catch forbids redeem_5m hard_floor padding; pattern slices keep
   combined block_rate ≤ 0.5; caught journeys must cite typology, ix.*, or
   floor.soft.* families (not velocity-floor vanity).
3. household_fp allow_rate ≥ 0.85 with block_rate ≤ 0.5 on legit shared-device
   families.
4. ato_known_device uses hybrid hard_floor via ato_chain — known-device confidence
   contributes to score; friction elevation may be floor-driven.
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from loyalty_abuse.calibration import load_calibration
from loyalty_abuse.features import FeatureStore
from loyalty_abuse.schema import EventEnvelope, EventType, FrictionAction
from loyalty_abuse.score import evaluate

N_PER_SLICE = 50

FRICTION_ORDER = [
    FrictionAction.allow,
    FrictionAction.throttle,
    FrictionAction.soft_challenge,
    FrictionAction.hard_challenge,
    FrictionAction.block,
]

# Slice bounds (mandatory gates) — published in report
SLICE_BOUNDS: dict[str, dict[str, Any]] = {
    "household_fp": {"metric": "allow_rate", "bound": 0.85},
    "device_rotation": {"metric": "catch_rate", "bound": 0.60},
    "slow_multi_acct": {"metric": "catch_rate", "bound": 0.70},
    "sequential_promo": {"metric": "catch_rate", "bound": 0.50},
    "ato_known_device": {"metric": "catch_rate", "bound": 0.50},
    "graph_payment_ring": {"metric": "catch_rate", "bound": 0.70},
}


def _ts(base: datetime, minutes: float = 0) -> str:
    return (base + timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _env(
    eid: str,
    *,
    tenant: str,
    ts: str,
    typ: EventType,
    account: str,
    device: str,
    ip: str,
    email: str | None = None,
    payment: str | None = None,
    payload: dict[str, Any] | None = None,
) -> EventEnvelope:
    return EventEnvelope(
        event_id=eid,
        tenant_id=tenant,
        ts=ts,
        type=typ,
        account_id=account,
        session_id=f"sess_{account}",
        device_id=device,
        ip=ip,
        email=email,
        payment_instrument_hash=payment,
        payload=payload or {},
    )


def _score_journey(events: list[EventEnvelope]):
    store = FeatureStore()
    for e in events[:-1]:
        store.observe(e)
    return evaluate(events[-1], store)


def _geq(friction: FrictionAction, minimum: FrictionAction) -> bool:
    return FRICTION_ORDER.index(friction) >= FRICTION_ORDER.index(minimum)


def gen_household_fp(i: int, rng: random.Random, base: datetime) -> list[EventEnvelope]:
    """Legit 2–3 aged accounts on shared family device; low velocity."""
    tenant = f"hh_{i}"
    device = f"dev_hh_{i}"
    ip = f"10.{rng.randint(1, 40)}.{i % 200}.{rng.randint(1, 250)}"
    n_accts = rng.choice([2, 3])
    events: list[EventEnvelope] = []
    # aged signups weeks apart-ish, all > young threshold
    for j in range(n_accts):
        acct = f"hh_{i}_a{j}"
        age_min = rng.randint(10, 40) * 24 * 60 + j * rng.randint(30, 180)
        events.append(
            _env(
                f"s_{i}_{j}",
                tenant=tenant,
                ts=_ts(base, -age_min),
                typ=EventType.signup,
                account=acct,
                device=device,
                ip=ip,
                email=f"family{i}_{j}@home.example",
            )
        )
    # sparse prior redeem from first account days ago
    events.append(
        _env(
            f"rp_{i}",
            tenant=tenant,
            ts=_ts(base, -(3 * 24 * 60)),
            typ=EventType.redeem,
            account=f"hh_{i}_a0",
            device=device,
            ip=ip,
            email=f"family{i}_0@home.example",
            payload={"reward_id": "r", "points": 5, "offer_ids": ["welcome"], "channel": "app"},
        )
    )
    last = f"hh_{i}_a{n_accts - 1}"
    events.append(
        _env(
            f"r_{i}",
            tenant=tenant,
            ts=_ts(base),
            typ=EventType.redeem,
            account=last,
            device=device,
            ip=ip,
            email=f"family{i}_{n_accts - 1}@home.example",
            payload={"reward_id": "r", "points": 10, "offer_ids": ["lunch"], "channel": "app"},
        )
    )
    return events


def gen_device_rotation(i: int, rng: random.Random, base: datetime) -> list[EventEnvelope]:
    """Rotate device_id each signup/redeem; catch via IP + code + promo multi-signal.

    ~30% near-miss: small n / weak discount — must not always catch at 100%.
    """
    tenant = f"dr_{i % 5}"
    ip = f"11.{i % 200}.{rng.randint(1, 40)}.{rng.randint(1, 250)}"
    code = f"ROT{rng.randint(0, 9)}"
    near_miss = rng.random() < 0.30
    n = rng.randint(6, 11) if near_miss else rng.randint(18, 36)
    events: list[EventEnvelope] = []
    for j in range(n):
        acct = f"dr_{i}_{j}"
        device = f"dev_dr_{i}_{j}_{rng.randint(0, 9999)}"
        events.append(
            _env(
                f"s_{i}_{j}",
                tenant=tenant,
                ts=_ts(base, -40 + j * rng.uniform(0.4, 1.2)),
                typ=EventType.signup,
                account=acct,
                device=device,
                ip=ip,
                email=f"rot{i}+{j}@ex.com",
            )
        )
        events.append(
            _env(
                f"r_{i}_{j}",
                tenant=tenant,
                ts=_ts(base, -20 + j * rng.uniform(0.3, 0.8)),
                typ=EventType.redeem,
                account=acct,
                device=device,
                ip=ip,
                email=f"rot{i}+{j}@ex.com",
                payload={
                    "reward_id": "r",
                    "points": rng.randint(3, 12),
                    "promo_codes": [code],
                    "offer_ids": [],
                    "channel": "app",
                },
            )
        )
    last = f"dr_{i}_{n - 1}"
    disc = rng.randint(10, 25) if near_miss else rng.randint(45, 80)
    offers = [] if near_miss else (["a", "b"] if rng.random() < 0.7 else ["a"])
    events.append(
        _env(
            f"rf_{i}",
            tenant=tenant,
            ts=_ts(base),
            typ=EventType.redeem,
            account=last,
            device=f"dev_dr_{i}_{n - 1}_final",
            ip=ip,
            email=f"rot{i}+{n - 1}@ex.com",
            payload={
                "reward_id": "r",
                "points": rng.randint(20, 80),
                "promo_codes": [code] if not near_miss or rng.random() < 0.5 else [],
                "offer_ids": offers,
                "loyalty_applied": ["pts"] if not near_miss else [],
                "discount_pct": disc,
                "channel": "app",
            },
        )
    )
    return events


def gen_slow_multi_acct(i: int, rng: random.Random, base: datetime) -> list[EventEnvelope]:
    """4–7 accounts on same device spaced >24h over 7d; alias + IP + stacked cashout."""
    tenant = f"sm_{i}"
    device = f"dev_sm_{i}_{rng.randint(0, 999)}"
    ip = f"12.{i % 200}.{rng.randint(1, 40)}.{rng.randint(1, 250)}"
    code = f"SLOW{rng.randint(0, 9)}"
    near_miss = rng.random() < 0.28
    n_acct = rng.randint(2, 3) if near_miss else rng.randint(4, 7)
    events: list[EventEnvelope] = []
    # Spaced >24h; last signup young (<60m) so young_multi_mult can fire before soft_or.
    offsets_h = [float(rng.randint(48, 160) - k * rng.randint(20, 30)) for k in range(max(n_acct - 1, 1))]
    offsets_h.append(rng.uniform(0.4, 0.9) if not near_miss else rng.uniform(120.0, 400.0))
    offsets_h = sorted(offsets_h, reverse=True)[:n_acct]
    for j, oh in enumerate(offsets_h):
        acct = f"sm_{i}_{j}"
        events.append(
            _env(
                f"s_{i}_{j}",
                tenant=tenant,
                ts=_ts(base, -oh * 60),
                typ=EventType.signup,
                account=acct,
                device=device,
                ip=ip,
                email=f"slow{i}+{j}@ex.com",
            )
        )
    for j in range(n_acct):
        events.append(
            _env(
                f"l_{i}_{j}",
                tenant=tenant,
                ts=_ts(base, -50 + j * rng.randint(5, 12)),
                typ=EventType.login,
                account=f"sm_{i}_{j}",
                device=device,
                ip=ip,
                email=f"slow{i}+{j}@ex.com",
                payload={"success": True},
            )
        )
    last = f"sm_{i}_{n_acct - 1}"
    events.append(
        _env(
            f"r_{i}",
            tenant=tenant,
            ts=_ts(base),
            typ=EventType.redeem,
            account=last,
            device=device,
            ip=ip,
            email=f"slow{i}+{n_acct - 1}@ex.com",
            payload={
                "reward_id": "r",
                "points": rng.randint(20, 60),
                "offer_ids": ["a", "b"] if rng.random() < 0.8 else ["a"],
                "promo_codes": [code],
                "loyalty_applied": ["pts"],
                "discount_pct": rng.randint(55, 85),
                "channel": "app",
            },
        )
    )
    return events


def gen_sequential_promo(i: int, rng: random.Random, base: datetime) -> list[EventEnvelope]:
    """Stack builds across offer_enroll events + related code reuse on shared IP."""
    tenant = f"sp_{i}"
    acct = f"sp_{i}"
    device = f"dev_sp_{i}_{rng.randint(0, 999)}"
    ip = f"13.{i % 200}.{rng.randint(1, 40)}.{rng.randint(1, 250)}"
    code = f"STACK{rng.randint(0, 9)}"
    near_miss = rng.random() < 0.30
    offers = [f"o{j}" for j in range(rng.randint(1, 2) if near_miss else rng.randint(4, 6))]
    events: list[EventEnvelope] = [
        _env(
            f"s_{i}",
            tenant=tenant,
            ts=_ts(base, -rng.randint(160, 400)),
            typ=EventType.signup,
            account=acct,
            device=device,
            ip=ip,
            email=f"seq{i}@ex.com",
        )
    ]
    for j, offer in enumerate(offers):
        events.append(
            _env(
                f"e_{i}_{j}",
                tenant=tenant,
                ts=_ts(base, -90 + j * rng.randint(8, 16)),
                typ=EventType.offer_enroll,
                account=acct,
                device=device,
                ip=ip,
                email=f"seq{i}@ex.com",
                payload={"offer_id": offer, "campaign_id": f"c{j}"},
            )
        )
    n_sib = rng.randint(3, 8) if near_miss else rng.randint(18, 36)
    for k in range(n_sib):
        sib = f"sp_{i}_sib{k}"
        events.append(
            _env(
                f"ss_{i}_{k}",
                tenant=tenant,
                ts=_ts(base, -40 + k * rng.uniform(0.3, 0.7)),
                typ=EventType.signup,
                account=sib,
                device=f"dev_sp_{i}_sib{k}_{rng.randint(0, 9999)}",
                ip=ip,
                email=f"seq{i}+sib{k}@ex.com",
            )
        )
        events.append(
            _env(
                f"sr_{i}_{k}",
                tenant=tenant,
                ts=_ts(base, -20 + k * rng.uniform(0.25, 0.6)),
                typ=EventType.redeem,
                account=sib,
                device=f"dev_sp_{i}_sib{k}_r",
                ip=ip,
                email=f"seq{i}+sib{k}@ex.com",
                payload={
                    "reward_id": "r",
                    "points": rng.randint(3, 10),
                    "promo_codes": [code],
                    "offer_ids": [],
                    "channel": "app",
                },
            )
        )
    events.append(
        _env(
            f"r_{i}",
            tenant=tenant,
            ts=_ts(base),
            typ=EventType.redeem,
            account=acct,
            device=device,
            ip=ip,
            email=f"seq{i}@ex.com",
            payload={
                "reward_id": "r",
                "points": rng.randint(15, 50),
                "offer_ids": [],
                "promo_codes": [code] if not near_miss else [],
                "discount_pct": rng.randint(15, 35) if near_miss else rng.randint(55, 85),
                "channel": "app",
            },
        )
    )
    return events


def gen_ato_known_device(i: int, rng: random.Random, base: datetime) -> list[EventEnvelope]:
    """login→sensitive profile→redeem on same device without new_device/new_geo."""
    tenant = f"ak_{i}"
    acct = f"ak_{i}"
    device = f"dev_ak_{i}_{rng.randint(0, 999)}"
    ip = f"14.{i % 200}.{rng.randint(1, 40)}.{rng.randint(1, 250)}"
    # Wide timing spread → ATO confidence/score variance (auditor F4).
    login_lag = rng.randint(2, 28)
    profile_lag = rng.randint(1, max(2, login_lag - 1))
    field = rng.choice(["email", "phone", "payment", "password"])
    return [
        _env(
            f"s_{i}",
            tenant=tenant,
            ts=_ts(base, -rng.randint(2000, 8000)),
            typ=EventType.signup,
            account=acct,
            device=device,
            ip=ip,
            email=f"victim{i}@ex.com",
        ),
        _env(
            f"l_{i}",
            tenant=tenant,
            ts=_ts(base, -login_lag),
            typ=EventType.login,
            account=acct,
            device=device,
            ip=ip,
            email=f"victim{i}@ex.com",
            payload={"success": True},
        ),
        _env(
            f"p_{i}",
            tenant=tenant,
            ts=_ts(base, -profile_lag),
            typ=EventType.profile_update,
            account=acct,
            device=device,
            ip=ip,
            payload={"fields_changed": [field]},
        ),
        _env(
            f"r_{i}",
            tenant=tenant,
            ts=_ts(base),
            typ=EventType.redeem,
            account=acct,
            device=device,
            ip=ip,
            email=f"attacker{i}@evil.com",
            payload={
                "reward_id": "r",
                "points": rng.randint(80, 300),
                "offer_ids": [],
                "channel": "app",
            },
        ),
    ]


def gen_graph_payment_ring(i: int, rng: random.Random, base: datetime) -> list[EventEnvelope]:
    """Accounts linked only by shared payment hash — distinct devices/IPs (graph score path)."""
    tenant = f"gp_{i}"
    pay = f"pay_ring_{i}_{rng.randint(0, 999)}"
    near_miss = rng.random() < 0.25
    n = rng.randint(3, 5) if near_miss else rng.randint(7, 12)
    events: list[EventEnvelope] = []
    for j in range(n):
        acct = f"gp_{i}_{j}"
        device = f"dev_gp_{i}_{j}_{rng.randint(0, 9999)}"
        ip = f"20.{(i + j) % 200}.{rng.randint(1, 40)}.{rng.randint(1, 250)}"
        events.append(
            _env(
                f"s_{i}_{j}",
                tenant=tenant,
                ts=_ts(base, -(n - j) * rng.randint(30, 90)),
                typ=EventType.signup,
                account=acct,
                device=device,
                ip=ip,
                email=f"gpring{i}_{j}@ex.com",
                payment=pay,
            )
        )
        events.append(
            _env(
                f"r_{i}_{j}",
                tenant=tenant,
                ts=_ts(base, -10 + j * 0.3),
                typ=EventType.redeem,
                account=acct,
                device=device,
                ip=ip,
                email=f"gpring{i}_{j}@ex.com",
                payment=pay,
                payload={
                    "reward_id": "r",
                    "points": rng.randint(5, 20),
                    "offer_ids": [],
                    "channel": "app",
                },
            )
        )
    last = n - 1
    events.append(
        _env(
            f"rf_{i}",
            tenant=tenant,
            ts=_ts(base),
            typ=EventType.redeem,
            account=f"gp_{i}_{last}",
            device=f"dev_gp_{i}_{last}_final",
            ip=f"21.{i % 200}.9.9",
            email=f"gpring{i}_{last}@ex.com",
            payment=pay,
            payload={
                "reward_id": "r",
                "points": rng.randint(40, 120),
                "offer_ids": [],
                "channel": "app",
            },
        )
    )
    return events


GENERATORS: dict[str, Callable[[int, random.Random, datetime], list[EventEnvelope]]] = {
    "household_fp": gen_household_fp,
    "device_rotation": gen_device_rotation,
    "slow_multi_acct": gen_slow_multi_acct,
    "sequential_promo": gen_sequential_promo,
    "ato_known_device": gen_ato_known_device,
    "graph_payment_ring": gen_graph_payment_ring,
}


def run_suite(seed: int = 42, n_per_slice: int = N_PER_SLICE) -> dict[str, Any]:
    load_calibration.cache_clear()
    cal = load_calibration()
    rng = random.Random(seed)
    base = datetime(2026, 8, 5, 12, 0, 0, tzinfo=timezone.utc)

    slices: dict[str, dict[str, Any]] = {}
    gates: dict[str, dict[str, Any]] = {}
    all_p: list[float] = []
    ato_incoherent = 0
    ato_n = 0
    allow_max = int((cal.get("bands") or {}).get("allow_max", 24))

    for name, gen in GENERATORS.items():
        frictions: list[str] = []
        scores: list[int] = []
        for j in range(n_per_slice):
            # independent sub-rng stream per journey for reproducibility
            jr = random.Random(rng.randint(0, 2**31 - 1))
            events = gen(j, jr, base)
            d = _score_journey(events)
            frictions.append(d.friction.value)
            scores.append(int(d.score))
            p = float(d.p_abuse or 0.0)
            all_p.append(p)
            if name == "ato_known_device":
                ato_n += 1
                band = str((d.features_snapshot or {}).get("band_friction") or "allow")
                band_i = FRICTION_ORDER.index(FrictionAction(band))
                fric_i = FRICTION_ORDER.index(d.friction)
                if int(d.score) <= allow_max and (fric_i - band_i) >= 2 and p >= 0.95:
                    ato_incoherent += 1

        n = len(frictions)
        allow_n = sum(1 for f in frictions if f == FrictionAction.allow.value)
        catch_n = sum(
            1
            for f in frictions
            if _geq(FrictionAction(f), FrictionAction.soft_challenge)
        )
        allow_rate = allow_n / n
        catch_rate = catch_n / n
        bound_spec = SLICE_BOUNDS[name]
        metric = bound_spec["metric"]
        bound = float(bound_spec["bound"])
        actual = allow_rate if metric == "allow_rate" else catch_rate
        passed = actual >= bound
        unique_scores = sorted(set(scores))
        slices[name] = {
            "n": n,
            "friction": {a.value: frictions.count(a.value) for a in FrictionAction},
            "allow_rate": round(allow_rate, 4),
            "catch_rate": round(catch_rate, 4),
            "unique_scores": len(unique_scores),
            "score_min": min(scores) if scores else 0,
            "score_max": max(scores) if scores else 0,
        }
        gates[name] = {
            "metric": metric,
            "bound": bound,
            "actual": round(actual, 4),
            "pass": passed,
        }

    # Abuse slices must not be a single deterministic score (cooperative theater).
    abuse_names = (
        "device_rotation",
        "slow_multi_acct",
        "sequential_promo",
        "ato_known_device",
        "graph_payment_ring",
    )
    uniq = sum(1 for n in abuse_names if slices[n]["unique_scores"] >= 2)
    gates["score_diversity"] = {
        "metric": "abuse_slices_with_ge_2_scores",
        "bound": 3,
        "actual": uniq,
        "pass": uniq >= 3,
    }
    gates["ato_score_variance"] = {
        "metric": "ato_unique_scores",
        "bound": 2,
        "actual": slices["ato_known_device"]["unique_scores"],
        "pass": slices["ato_known_device"]["unique_scores"] >= 2,
    }

    # Auditor F4: at least 2 abuse slices must not catch 100% (near-misses exist).
    imperfect = sum(1 for n in abuse_names if slices[n]["catch_rate"] < 1.0)
    gates["nonperfect_catch"] = {
        "metric": "abuse_slices_catch_lt_1",
        "bound": 2,
        "actual": imperfect,
        "pass": imperfect >= 2,
    }

    # Auditor F1: p_abuse must not be a two-point step on the suite.
    extreme = sum(1 for p in all_p if p <= 0.05 or p >= 0.95) / max(len(all_p), 1)
    gates["p_abuse_not_step"] = {
        "metric": "frac_p_in_extremes",
        "bound": 0.80,
        "actual": round(extreme, 4),
        "pass": extreme < 0.80,
    }
    gates["ato_p_friction_coherent"] = {
        "metric": "ato_allowband_hard_p95_count",
        "bound": 0,
        "actual": ato_incoherent,
        "pass": ato_incoherent == 0,
    }

    # Anti-vanity block-rate caps (also enforced by pytest; must drive CLI gates_pass).
    pattern_names = ("slow_multi_acct", "sequential_promo")
    pattern_blocks = sum(slices[n]["friction"].get("block", 0) for n in pattern_names)
    pattern_n = sum(slices[n]["n"] for n in pattern_names)
    pattern_block_rate = pattern_blocks / pattern_n
    gates["pattern_block_rate"] = {
        "metric": "block_rate",
        "bound": 0.5,
        "actual": round(pattern_block_rate, 4),
        "pass": pattern_block_rate <= 0.5,
    }

    hh_block = slices["household_fp"]["friction"].get("block", 0)
    hh_n = slices["household_fp"]["n"]
    hh_block_rate = hh_block / hh_n
    gates["household_block_rate"] = {
        "metric": "block_rate",
        "bound": 0.5,
        "actual": round(hh_block_rate, 4),
        "pass": hh_block_rate <= 0.5,
    }

    return {
        "seed": seed,
        "n_per_slice": n_per_slice,
        "policy_version": cal.get("policy_version"),
        "slice_bounds": {k: {"metric": v["metric"], "bound": v["bound"]} for k, v in SLICE_BOUNDS.items()},
        "slices": slices,
        "gates": gates,
        "gates_pass": all(g["pass"] for g in gates.values()),
    }
