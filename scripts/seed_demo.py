#!/usr/bin/env python3
"""Seed demo decisions via HTTP — prior events ingest-only, final event evaluates."""

from __future__ import annotations

import os
import sys

import httpx

BASE_URL = os.environ.get("BASE_URL", "http://127.0.0.1:8080")
TENANT = "demo"


def _base(account_id: str, event_id: str, ts: str, **extra: object) -> dict:
    ev = {
        "event_id": event_id,
        "tenant_id": TENANT,
        "ts": ts,
        "account_id": account_id,
        "session_id": f"s_{account_id}",
        "device_id": extra.pop("device_id", f"d_{account_id}"),
        "ip": extra.pop("ip", "1.1.1.1"),
        "payload": extra.pop("payload", {}),
    }
    ev.update(extra)
    return ev


def post_sequence(client: httpx.Client, label: str, events: list[dict]) -> dict:
    if not events:
        raise ValueError(f"{label}: empty sequence")
    for event in events[:-1]:
        r = client.post(f"{BASE_URL}/v1/events", json={**event, "evaluate": False}, timeout=30.0)
        r.raise_for_status()
    r = client.post(f"{BASE_URL}/v1/events", json={**events[-1], "evaluate": True}, timeout=30.0)
    r.raise_for_status()
    decision = r.json()
    print(f"{label}: score={decision.get('score')} friction={decision.get('friction')}")
    return decision


def clean_user_events() -> list[dict]:
    return [
        _base("clean_a", "clean_s1", "2026-08-01T00:00:00Z", type="signup"),
        _base(
            "clean_a",
            "clean_r1",
            "2026-08-04T12:00:00Z",
            type="redeem",
            payload={"reward_id": "r", "points": 10, "offer_ids": ["one"], "channel": "app"},
        ),
    ]


def multi_account_events() -> list[dict]:
    dev = "dev_multi"
    return [
        _base("ma_a1", "ma_s1", "2026-08-04T12:00:00Z", type="signup", device_id=dev),
        _base("ma_a2", "ma_s2", "2026-08-04T12:01:00Z", type="signup", device_id=dev),
        _base("ma_a3", "ma_s3", "2026-08-04T12:02:00Z", type="signup", device_id=dev),
        _base(
            "ma_a3",
            "ma_r1",
            "2026-08-04T12:03:00Z",
            type="redeem",
            device_id=dev,
            payload={"reward_id": "r", "points": 10, "offer_ids": ["one"], "channel": "app"},
        ),
    ]


def referral_self_deal_events() -> list[dict]:
    shared = "dev_ref"
    pay = "pay_ref"
    return [
        _base(
            "ref_ref",
            "rf_s1",
            "2026-08-04T11:00:00Z",
            type="signup",
            device_id=shared,
            payment_instrument_hash=pay,
        ),
        _base(
            "ref_ree",
            "rf_s2",
            "2026-08-04T11:01:00Z",
            type="signup",
            device_id=shared,
            payment_instrument_hash=pay,
        ),
        _base(
            "ref_ree",
            "rf_ev1",
            "2026-08-04T12:00:00Z",
            type="referral",
            device_id=shared,
            payment_instrument_hash=pay,
            payload={"referrer_id": "ref_ref", "referee_id": "ref_ree"},
        ),
    ]


def promo_stack_events() -> list[dict]:
    return [
        _base("ps_a1", "ps_s1", "2026-08-04T12:00:00Z", type="signup"),
        _base(
            "ps_a1",
            "ps_r1",
            "2026-08-04T12:05:00Z",
            type="redeem",
            payload={
                "reward_id": "r",
                "points": 50,
                "offer_ids": ["o1", "o2", "o3"],
                "promo_codes": ["stack1"],
                "discount_pct": 55,
                "channel": "app",
            },
        ),
    ]


def bot_redeem_events() -> list[dict]:
    dev = "botdev"
    events: list[dict] = [
        _base("bot_a1", "bot_s1", "2026-08-04T12:00:00Z", type="signup", device_id=dev, email="bot@example.com"),
        _base(
            "bot_a2",
            "bot_s2",
            "2026-08-04T12:00:10Z",
            type="signup",
            device_id=dev,
            email="bot+2@example.com",
        ),
        _base(
            "bot_a3",
            "bot_s3",
            "2026-08-04T12:00:20Z",
            type="signup",
            device_id=dev,
            email="bot+3@example.com",
        ),
    ]
    for i in range(1, 10):
        events.append(
            _base(
                "bot_a1",
                f"bot_r{i}",
                f"2026-08-04T12:01:{(i - 1) * 5:02d}Z",
                type="redeem",
                device_id=dev,
                payload={"reward_id": "r", "points": 1, "offer_ids": [], "channel": "app"},
            )
        )
    events.append(
        _base(
            "bot_a1",
            "bot_r10",
            "2026-08-04T12:01:45Z",
            type="redeem",
            device_id=dev,
            payload={
                "reward_id": "r",
                "points": 1,
                "offer_ids": ["o1", "o2"],
                "promo_codes": ["p1"],
                "discount_pct": 50,
                "channel": "app",
            },
        )
    )
    return events


def code_leak_events() -> list[dict]:
    code = "LEAK50"
    events: list[dict] = []
    for i in range(25):
        events.append(
            _base(
                f"cl_a{i}",
                f"cl_s{i}",
                f"2026-08-04T10:{i:02d}:00Z",
                type="signup",
                payload={"referral_code": code},
            )
        )
    events.append(
        _base(
            "cl_a25",
            "cl_ck1",
            "2026-08-04T11:00:00Z",
            type="checkout",
            payload={"order_id": "ord1", "amount": 12.5, "promo_codes": [code], "loyalty_applied": []},
        )
    )
    return events


def ato_redeem_events() -> list[dict]:
    return [
        _base("ato_a1", "ato_s1", "2026-08-04T10:00:00Z", type="signup", device_id="old_dev"),
        _base(
            "ato_a1",
            "ato_l1",
            "2026-08-04T12:00:00Z",
            type="login",
            device_id="new_dev",
            ip="9.9.9.9",
            payload={"success": True, "new_device": True, "geo": "XX"},
        ),
        _base(
            "ato_a1",
            "ato_p1",
            "2026-08-04T12:01:00Z",
            type="profile_update",
            device_id="new_dev",
            ip="9.9.9.9",
            payload={"fields_changed": ["email"]},
        ),
        _base(
            "ato_a1",
            "ato_r1",
            "2026-08-04T12:02:00Z",
            type="redeem",
            device_id="new_dev",
            ip="9.9.9.9",
            payload={"reward_id": "r", "points": 50, "offer_ids": [], "channel": "app"},
        ),
    ]


def main() -> int:
    sequences = [
        ("clean", clean_user_events()),
        ("clean_2", clean_user_events()),  # second clean user with distinct ids
        ("multi_account", multi_account_events()),
        ("referral_self_deal", referral_self_deal_events()),
        ("promo_stack", promo_stack_events()),
        ("bot_redeem", bot_redeem_events()),
        ("code_leak", code_leak_events()),
        ("ato_redeem", ato_redeem_events()),
    ]
    # Give clean_2 unique event ids so they don't collide with clean
    sequences[1] = (
        "clean_2",
        [
            _base("clean_b", "clean2_s1", "2026-08-01T01:00:00Z", type="signup"),
            _base(
                "clean_b",
                "clean2_r1",
                "2026-08-04T13:00:00Z",
                type="redeem",
                payload={"reward_id": "r", "points": 10, "offer_ids": ["one"], "channel": "app"},
            ),
        ],
    )

    try:
        with httpx.Client() as client:
            health = client.get(f"{BASE_URL}/docs", timeout=5.0)
            health.raise_for_status()
    except httpx.HTTPError as exc:
        print(f"API unreachable at {BASE_URL}: {exc}", file=sys.stderr)
        return 1

    with httpx.Client() as client:
        for label, events in sequences:
            post_sequence(client, label, events)

    print(f"Seeded {len(sequences)} scenarios against {BASE_URL}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
