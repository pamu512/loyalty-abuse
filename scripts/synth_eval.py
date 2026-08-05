#!/usr/bin/env python3
"""Generate labeled synthetic journeys and evaluate friction_v1_1 offline."""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from loyalty_abuse.calibration import load_calibration  # noqa: E402
from loyalty_abuse.features import FeatureStore  # noqa: E402
from loyalty_abuse.schema import EventEnvelope, EventType, FrictionAction  # noqa: E402
from loyalty_abuse.score import evaluate  # noqa: E402

FRICTION_ORDER = [
    FrictionAction.allow,
    FrictionAction.throttle,
    FrictionAction.soft_challenge,
    FrictionAction.hard_challenge,
    FrictionAction.block,
]

MIX = [
    ("clean", 0.70),
    ("multi_account", 0.06),
    ("referral_self_deal", 0.04),
    ("promo_stack", 0.04),
    ("bot_redeem", 0.05),
    ("code_leak", 0.04),
    ("ato_redeem", 0.04),
    ("mixed_hard", 0.03),
]

GATES = {
    "clean_allow_rate": 0.95,
    "ato_hard_plus": 0.90,
    "bot_throttle_plus": 0.85,
    "multi_throttle_plus": 0.80,
    "soft_plus_precision": 0.70,
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


@dataclass
class Subject:
    label: str
    events: list[EventEnvelope]


def _alloc(n: int, rng: random.Random) -> list[str]:
    labels: list[str] = []
    for name, share in MIX:
        labels.extend([name] * int(round(n * share)))
    while len(labels) < n:
        labels.append("clean")
    labels = labels[:n]
    rng.shuffle(labels)
    return labels


def gen_clean(i: int, rng: random.Random, base: datetime) -> Subject:
    tenant = f"t_{i % 50}"
    acct = f"clean_{i}"
    device = f"dev_clean_{i}"
    ip = f"10.{(i // 256) % 256}.{i % 256}.1"
    events = [
        _env(f"s_{i}", tenant=tenant, ts=_ts(base, -rng.randint(120, 10000)), typ=EventType.signup, account=acct, device=device, ip=ip, email=f"u{i}@mail.com"),
        _env(
            f"r_{i}",
            tenant=tenant,
            ts=_ts(base),
            typ=EventType.redeem,
            account=acct,
            device=device,
            ip=ip,
            email=f"u{i}@mail.com",
            payload={"reward_id": "r", "points": 10, "offer_ids": ["welcome"], "channel": "app"},
        ),
    ]
    return Subject("clean", events)


def gen_multi(i: int, rng: random.Random, base: datetime) -> Subject:
    tenant = f"t_{i % 20}"
    device = f"dev_multi_{i}"
    ip = f"11.{i % 250}.0.1"
    n_accts = rng.randint(3, 10)
    events: list[EventEnvelope] = []
    for j in range(n_accts):
        acct = f"ma_{i}_{j}"
        email = f"farm{i}+{j}@ex.com"
        events.append(
            _env(
                f"s_{i}_{j}",
                tenant=tenant,
                ts=_ts(base, -30 + j),
                typ=EventType.signup,
                account=acct,
                device=device,
                ip=ip,
                email=email,
            )
        )
    last = f"ma_{i}_{n_accts - 1}"
    events.append(
        _env(
            f"r_{i}",
            tenant=tenant,
            ts=_ts(base),
            typ=EventType.redeem,
            account=last,
            device=device,
            ip=ip,
            email=f"farm{i}+x@ex.com",
            payload={"reward_id": "r", "points": 50, "offer_ids": ["welcome"], "channel": "app"},
        )
    )
    return Subject("multi_account", events)


def gen_referral(i: int, rng: random.Random, base: datetime) -> Subject:
    tenant = f"t_{i % 20}"
    device = f"dev_ref_{i}"
    pay = f"pay_ref_{i}"
    ref, ree = f"ref_{i}_a", f"ref_{i}_b"
    events = [
        _env(f"s_a_{i}", tenant=tenant, ts=_ts(base, -40), typ=EventType.signup, account=ref, device=device, ip="12.0.0.1", payment=pay, email=f"a{i}@ex.com"),
        _env(f"s_b_{i}", tenant=tenant, ts=_ts(base, -20), typ=EventType.signup, account=ree, device=device, ip="12.0.0.2", payment=pay, email=f"b{i}@ex.com"),
        _env(
            f"ref_{i}",
            tenant=tenant,
            ts=_ts(base),
            typ=EventType.referral,
            account=ree,
            device=device,
            ip="12.0.0.2",
            payment=pay,
            payload={"referrer_id": ref, "referee_id": ree},
        ),
    ]
    return Subject("referral_self_deal", events)


def gen_promo(i: int, rng: random.Random, base: datetime) -> Subject:
    tenant = f"t_{i % 20}"
    acct = f"promo_{i}"
    device = f"dev_promo_{i}"
    events = [
        _env(f"s_{i}", tenant=tenant, ts=_ts(base, -500), typ=EventType.signup, account=acct, device=device, ip="13.0.0.1", email=f"p{i}@ex.com"),
        _env(
            f"c_{i}",
            tenant=tenant,
            ts=_ts(base),
            typ=EventType.checkout,
            account=acct,
            device=device,
            ip="13.0.0.1",
            payload={
                "order_id": f"o{i}",
                "amount": 5.0,
                "offer_ids": ["a", "b"],
                "promo_codes": ["X"],
                "loyalty_applied": ["pts"],
                "discount_pct": rng.randint(45, 80),
            },
        ),
    ]
    return Subject("promo_stack", events)


def gen_bot(i: int, rng: random.Random, base: datetime) -> Subject:
    tenant = f"t_{i % 20}"
    device = f"dev_bot_{i}"
    ip = f"14.{i % 200}.1.1"
    events: list[EventEnvelope] = []
    n = rng.randint(10, 18)
    for j in range(n):
        acct = f"bot_{i}_{j}"
        events.append(
            _env(
                f"s_{i}_{j}",
                tenant=tenant,
                ts=_ts(base, -4 + j * 0.2),
                typ=EventType.signup,
                account=acct,
                device=device,
                ip=ip,
                email=f"bot{i}_{j}@ex.com",
            )
        )
    events.append(
        _env(
            f"r_{i}",
            tenant=tenant,
            ts=_ts(base),
            typ=EventType.redeem,
            account=f"bot_{i}_{n - 1}",
            device=device,
            ip=ip,
            payload={"reward_id": "r", "points": 1, "offer_ids": [], "channel": "app"},
        )
    )
    # add burst redeems
    for j in range(rng.randint(8, 14)):
        events.insert(
            -1,
            _env(
                f"rr_{i}_{j}",
                tenant=tenant,
                ts=_ts(base, -1 + j * 0.1),
                typ=EventType.redeem,
                account=f"bot_{i}_{min(j, n - 1)}",
                device=device,
                ip=ip,
                payload={"reward_id": "r", "points": 1, "offer_ids": [], "channel": "app"},
            ),
        )
    return Subject("bot_redeem", events)


def gen_code_leak(i: int, rng: random.Random, base: datetime) -> Subject:
    tenant = f"t_code_{i % 5}"
    code = f"LEAK{i % 7}"
    n = rng.randint(20, 55)
    events: list[EventEnvelope] = []
    for j in range(n):
        acct = f"cl_{i}_{j}"
        events.append(
            _env(
                f"s_{i}_{j}",
                tenant=tenant,
                ts=_ts(base, -200 + j),
                typ=EventType.signup,
                account=acct,
                device=f"dev_cl_{i}_{j}",
                ip=f"15.{j % 250}.0.1",
                email=f"cl{i}_{j}@ex.com",
            )
        )
        events.append(
            _env(
                f"r_{i}_{j}",
                tenant=tenant,
                ts=_ts(base, -100 + j),
                typ=EventType.redeem,
                account=acct,
                device=f"dev_cl_{i}_{j}",
                ip=f"15.{j % 250}.0.1",
                payload={"reward_id": "r", "points": 5, "promo_codes": [code], "offer_ids": [], "channel": "app"},
            )
        )
    last = f"cl_{i}_{n - 1}"
    events.append(
        _env(
            f"rf_{i}",
            tenant=tenant,
            ts=_ts(base),
            typ=EventType.redeem,
            account=last,
            device=f"dev_cl_{i}_{n - 1}",
            ip="15.1.1.1",
            payload={"reward_id": "r", "points": 5, "promo_codes": [code], "offer_ids": [], "channel": "app"},
        )
    )
    return Subject("code_leak", events)


def gen_ato(i: int, rng: random.Random, base: datetime) -> Subject:
    tenant = f"t_{i % 20}"
    acct = f"ato_{i}"
    events = [
        _env(f"s_{i}", tenant=tenant, ts=_ts(base, -1000), typ=EventType.signup, account=acct, device="old", ip="16.0.0.1", email=f"ato{i}@ex.com"),
        _env(
            f"l_{i}",
            tenant=tenant,
            ts=_ts(base, -10),
            typ=EventType.login,
            account=acct,
            device="new",
            ip="16.9.9.9",
            payload={"success": True, "new_device": True},
        ),
        _env(
            f"p_{i}",
            tenant=tenant,
            ts=_ts(base, -5),
            typ=EventType.profile_update,
            account=acct,
            device="new",
            ip="16.9.9.9",
            payload={"fields_changed": ["email"]},
        ),
        _env(
            f"r_{i}",
            tenant=tenant,
            ts=_ts(base),
            typ=EventType.redeem,
            account=acct,
            device="new",
            ip="16.9.9.9",
            payload={"reward_id": "r", "points": 200, "offer_ids": [], "channel": "app"},
        ),
    ]
    return Subject("ato_redeem", events)


def gen_mixed(i: int, rng: random.Random, base: datetime) -> Subject:
    # multi-account device + promo stack on last redeem
    s = gen_multi(i, rng, base)
    last = s.events[-1]
    last.payload = {
        "reward_id": "r",
        "points": 50,
        "offer_ids": ["a", "b", "c"],
        "promo_codes": ["Z"],
        "discount_pct": 60,
        "channel": "app",
    }
    return Subject("mixed_hard", s.events)


GENERATORS: dict[str, Callable[[int, random.Random, datetime], Subject]] = {
    "clean": gen_clean,
    "multi_account": gen_multi,
    "referral_self_deal": gen_referral,
    "promo_stack": gen_promo,
    "bot_redeem": gen_bot,
    "code_leak": gen_code_leak,
    "ato_redeem": gen_ato,
    "mixed_hard": gen_mixed,
}


def _geq(friction: str, minimum: str) -> bool:
    return FRICTION_ORDER.index(FrictionAction(friction)) >= FRICTION_ORDER.index(FrictionAction(minimum))


def run_eval(n: int, seed: int) -> dict[str, Any]:
    load_calibration.cache_clear()
    cal = load_calibration()
    rng = random.Random(seed)
    base = datetime(2026, 8, 4, 12, 0, 0, tzinfo=timezone.utc)
    labels = _alloc(n, rng)

    friction_counts: Counter[str] = Counter()
    score_hist: Counter[str] = Counter()
    reason_counts: Counter[str] = Counter()
    typology_hits: Counter[str] = Counter()
    by_label: dict[str, dict[str, Any]] = defaultdict(lambda: {"n": 0, "friction": Counter(), "scores": []})
    floor_by_label: Counter[str] = Counter()
    sample: list[dict[str, Any]] = []

    t0 = time.time()
    for idx, label in enumerate(labels):
        subj = GENERATORS[label](idx, rng, base)
        store = FeatureStore()
        for e in subj.events[:-1]:
            store.observe(e)
        d = evaluate(subj.events[-1], store)
        friction_counts[d.friction.value] += 1
        bucket = f"{(d.score // 10) * 10}-{(d.score // 10) * 10 + 9}" if d.score < 100 else "100"
        score_hist[bucket] += 1
        for r in d.reasons:
            reason_counts[r] += 1
        for tr in d.typology_breakdown:
            typology_hits[tr.id] += 1
        row = by_label[label]
        row["n"] += 1
        row["friction"][d.friction.value] += 1
        row["scores"].append(d.score)
        if d.features_snapshot.get("force_hard_floor"):
            floor_by_label[label] += 1
        if len(sample) < 1000 and (label != "clean" or rng.random() < 0.002):
            sample.append(
                {
                    "label": label,
                    "score": d.score,
                    "friction": d.friction.value,
                    "reasons": d.reasons,
                    "force_hard_floor": bool(d.features_snapshot.get("force_hard_floor")),
                }
            )
        if (idx + 1) % 25000 == 0:
            elapsed = time.time() - t0
            rate = (idx + 1) / elapsed
            print(f"... {idx + 1}/{n} ({rate:.0f}/s)", flush=True)

    elapsed = time.time() - t0

    def rate_for(label: str, min_friction: str) -> float:
        row = by_label[label]
        if row["n"] == 0:
            return 0.0
        ok = sum(c for f, c in row["friction"].items() if _geq(f, min_friction))
        return ok / row["n"]

    clean_allow = by_label["clean"]["friction"].get("allow", 0) / max(1, by_label["clean"]["n"])
    soft_plus = sum(friction_counts[f] for f in ("soft_challenge", "hard_challenge", "block"))
    soft_plus_nonclean = 0
    for lab, row in by_label.items():
        if lab == "clean":
            continue
        soft_plus_nonclean += sum(
            row["friction"].get(f, 0) for f in ("soft_challenge", "hard_challenge", "block")
        )
    precision = soft_plus_nonclean / soft_plus if soft_plus else 1.0

    metrics = {
        "clean_allow_rate": clean_allow,
        "ato_hard_plus": rate_for("ato_redeem", "hard_challenge"),
        "bot_throttle_plus": rate_for("bot_redeem", "throttle"),
        "multi_throttle_plus": rate_for("multi_account", "throttle"),
        "soft_plus_precision": precision,
    }
    gates = {k: {"target": GATES[k], "actual": metrics[k], "pass": metrics[k] >= GATES[k]} for k in GATES}

    return {
        "n": n,
        "seed": seed,
        "policy_version": cal["policy_version"],
        "elapsed_sec": round(elapsed, 3),
        "rate_per_sec": round(n / elapsed, 1) if elapsed else None,
        "friction_counts": dict(friction_counts),
        "score_histogram": dict(sorted(score_hist.items())),
        "top_reasons": reason_counts.most_common(20),
        "typology_hit_rates": {k: v / n for k, v in typology_hits.items()},
        "floor_rate_by_label": {k: floor_by_label[k] / by_label[k]["n"] for k in by_label},
        "by_label": {
            lab: {
                "n": row["n"],
                "friction": dict(row["friction"]),
                "mean_score": round(sum(row["scores"]) / row["n"], 2) if row["n"] else 0,
            }
            for lab, row in by_label.items()
        },
        "metrics": metrics,
        "gates": gates,
        "gates_pass": all(g["pass"] for g in gates.values()),
        "sample": sample,
    }


def compare(a_path: Path, b_path: Path) -> dict[str, Any]:
    a = json.loads(a_path.read_text())
    b = json.loads(b_path.read_text())
    return {
        "a": a_path.name,
        "b": b_path.name,
        "friction_counts": {"a": a.get("friction_counts"), "b": b.get("friction_counts")},
        "metrics": {"a": a.get("metrics"), "b": b.get("metrics")},
        "gates_pass": {"a": a.get("gates_pass"), "b": b.get("gates_pass")},
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--n", type=int, default=500_000)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--out", type=Path, default=Path("artifacts/synth_500k_v1_1.json"))
    p.add_argument("--compare", nargs=2, metavar=("A", "B"))
    args = p.parse_args()

    if args.compare:
        rep = compare(Path(args.compare[0]), Path(args.compare[1]))
        print(json.dumps(rep, indent=2))
        return 0

    args.out.parent.mkdir(parents=True, exist_ok=True)
    print(f"Running n={args.n} seed={args.seed} ...", flush=True)
    report = run_eval(args.n, args.seed)
    # trim sample in written file stays; write summary md
    args.out.write_text(json.dumps(report, indent=2))
    summary = args.out.with_name(args.out.stem + "_summary.md")
    lines = [
        f"# Synth eval {report['policy_version']}",
        "",
        f"- n={report['n']} seed={report['seed']}",
        f"- elapsed={report['elapsed_sec']}s ({report['rate_per_sec']}/s)",
        f"- gates_pass={report['gates_pass']}",
        "",
        "## Gates",
    ]
    for k, g in report["gates"].items():
        lines.append(f"- `{k}`: actual={g['actual']:.4f} target={g['target']} pass={g['pass']}")
    lines += ["", "## Friction counts", ""]
    for k, v in report["friction_counts"].items():
        lines.append(f"- {k}: {v}")
    lines += ["", "## Mean score by label", ""]
    for lab, row in sorted(report["by_label"].items()):
        lines.append(f"- {lab}: n={row['n']} mean_score={row['mean_score']} friction={row['friction']}")
    summary.write_text("\n".join(lines) + "\n")
    print(summary.read_text())
    print(f"Wrote {args.out}")
    return 0 if report["gates_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
