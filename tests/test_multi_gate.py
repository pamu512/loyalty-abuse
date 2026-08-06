"""Unit tests for loyalty economics multi-gate engine (standalone)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from loyalty_abuse.multi_gate import SCHEMA_ID, evaluate_loyalty_economics


def _cfg(**over):
    base = {
        "schema_id": "loyalty_abuse.loyalty_program_config/v1",
        "program_id": "default",
        "config_version": "1",
        "effective_at": "2026-01-01T00:00:00Z",
        "acquisition_cost_minor": 2500,
        "retention_cost_minor": 500,
        "target_loyalty_ltv_ratio": 0.12,
        "ineligible_above_ratio": 0.25,
        "restore_at_or_below_ratio": 0.12,
        "min_dwell_seconds": 86400,
        "window": "trailing_90d",
        "velocity_window": "trailing_7d",
        "new_member_grace_days": 0,
        "vip_entity_ids": [],
        "max_feed_age_seconds": 86400,
    }
    base.update(over)
    return base


def _complete_feeds(
    entity_id="e1", loyalty_cost=400, ltv_orders=1000, refunds=0, as_of=None
):
    as_of = as_of or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    return {
        "as_of": as_of,
        "orders": [
            {
                "entity_id": entity_id,
                "order_id": "o1",
                "ts": as_of,
                "amount_minor": ltv_orders,
                "currency": "USD",
                "status": "paid",
            }
        ],
        "refunds": (
            []
            if refunds == 0
            else [
                {
                    "entity_id": entity_id,
                    "order_id": "o1",
                    "ts": as_of,
                    "amount_minor": refunds,
                    "currency": "USD",
                }
            ]
        ),
        "loyalty_ledger": [
            {
                "entity_id": entity_id,
                "ts": as_of,
                "direction": "burn",
                "value_minor": loyalty_cost,
                "program_id": "default",
            }
        ],
        "lifecycle": [
            {
                "entity_id": entity_id,
                "created_at": "2025-01-01T00:00:00Z",
                "last_active_at": as_of,
            }
        ],
    }


def test_schema_and_missing_feeds():
    out = evaluate_loyalty_economics(
        entity_id="e1", feed_snapshot=None, program_config=_cfg()
    )
    assert out["schema_id"] == SCHEMA_ID
    assert out["status"] == "feeds_missing"
    assert out["gates"]["order"]["eligible"] is None
    assert out["policy"]["order_decision_untouched"] is True


def test_incomplete_without_ledger():
    snap = _complete_feeds()
    del snap["loyalty_ledger"]
    out = evaluate_loyalty_economics(
        entity_id="e1", feed_snapshot=snap, program_config=_cfg()
    )
    assert out["status"] == "feeds_incomplete"
    assert out["gates"]["dispatch"]["eligible"] is None


def test_config_missing():
    out = evaluate_loyalty_economics(
        entity_id="e1", feed_snapshot=_complete_feeds(), program_config=None
    )
    assert out["status"] == "config_missing"
    for gate in ("dispatch", "redeem", "order"):
        assert out["gates"][gate]["eligible"] is None


def test_stale_feed_all_gates_null():
    now = datetime(2026, 8, 6, 12, 0, tzinfo=timezone.utc)
    stale_as_of = (now - timedelta(seconds=90000)).isoformat().replace("+00:00", "Z")
    out = evaluate_loyalty_economics(
        entity_id="e1",
        feed_snapshot=_complete_feeds(as_of=stale_as_of),
        program_config=_cfg(max_feed_age_seconds=86400),
        now=now,
    )
    assert out["status"] == "stale"
    for gate in ("dispatch", "redeem", "order"):
        assert out["gates"][gate]["eligible"] is None


def test_ratio_breach_order_ineligible_dispatch_may_differ():
    out = evaluate_loyalty_economics(
        entity_id="e1",
        feed_snapshot=_complete_feeds(loyalty_cost=400, ltv_orders=1000),
        program_config=_cfg(),
        scope={"kind": "program", "id": "default"},
    )
    assert out["status"] in ("ok", "partial_derived")
    assert out["metrics"]["loyalty_ltv_ratio"] == 0.4
    assert out["gates"]["order"]["eligible"] is False
    assert out["gates"]["order"]["status"] == "ok"
    assert out["gates"]["dispatch"]["eligible"] is False
    assert out["gates"]["redeem"]["eligible"] is False


def test_healthy_ratio_all_eligible():
    out = evaluate_loyalty_economics(
        entity_id="e1",
        feed_snapshot=_complete_feeds(loyalty_cost=50, ltv_orders=1000),
        program_config=_cfg(),
    )
    assert out["status"] == "partial_derived"
    assert out["gates"]["order"]["eligible"] is True
    assert out["gates"]["redeem"]["eligible"] is True
    assert out["gates"]["dispatch"]["eligible"] is True


def test_hysteresis_requires_dwell():
    now = datetime(2026, 8, 6, 12, 0, tzinfo=timezone.utc)
    prior = {
        "ineligible_since": (now - timedelta(hours=1)).isoformat().replace("+00:00", "Z"),
        "restore_band_since": (now - timedelta(hours=1)).isoformat().replace("+00:00", "Z"),
    }
    out = evaluate_loyalty_economics(
        entity_id="e1",
        feed_snapshot=_complete_feeds(
            loyalty_cost=50,
            ltv_orders=1000,
            as_of=now.isoformat().replace("+00:00", "Z"),
        ),
        program_config=_cfg(min_dwell_seconds=86400),
        now=now,
        prior_gate_state=prior,
    )
    assert out["gates"]["order"]["eligible"] is False
    assert any("dwell" in r for r in out["gates"]["order"]["reasons"])


def test_vip_escape():
    out = evaluate_loyalty_economics(
        entity_id="vip1",
        feed_snapshot=_complete_feeds(
            entity_id="vip1", loyalty_cost=900, ltv_orders=1000
        ),
        program_config=_cfg(vip_entity_ids=["vip1"]),
    )
    assert out["gates"]["order"]["eligible"] is True
    assert any("vip" in r for r in out["gates"]["order"]["reasons"])


def test_cluster_unit_when_peers():
    out = evaluate_loyalty_economics(
        entity_id="e1",
        feed_snapshot=_complete_feeds(),
        program_config=_cfg(),
        cluster_entity_ids=["e1", "e2"],
    )
    assert out["unit"] == "cluster"


def test_dispatch_ineligible_order_eligible_with_policy():
    cfg = _cfg(
        gate_policies={
            "dispatch": {"churn_flips": True},
            "redeem": {"churn_flips": False},
            "order": {"churn_flips": False},
        }
    )
    snap = _complete_feeds(loyalty_cost=150, ltv_orders=1000)
    snap["lifecycle"] = [
        {
            "entity_id": "e1",
            "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "last_active_at": snap["as_of"],
        }
    ]
    out = evaluate_loyalty_economics(
        entity_id="e1", feed_snapshot=snap, program_config=cfg
    )
    assert out["metrics"]["loyalty_ltv_ratio"] == 0.15
    assert out["metrics"]["churn_proxy"]["flagged"] is True
    assert out["gates"]["order"]["eligible"] is True
    assert out["gates"]["dispatch"]["eligible"] is False
    assert "churn_proxy_above_target" in out["gates"]["dispatch"]["reasons"]
    assert "churn_proxy_above_target" not in out["gates"]["order"]["reasons"]


def test_cluster_rollup_includes_peer_entities():
    now = datetime(2026, 8, 6, 12, 0, tzinfo=timezone.utc)
    as_of = now.isoformat().replace("+00:00", "Z")
    snap = {
        "as_of": as_of,
        "orders": [
            {
                "entity_id": "e1",
                "order_id": "o1",
                "ts": as_of,
                "amount_minor": 500,
                "currency": "USD",
                "status": "paid",
            },
            {
                "entity_id": "e2",
                "order_id": "o2",
                "ts": as_of,
                "amount_minor": 500,
                "currency": "USD",
                "status": "paid",
            },
        ],
        "refunds": [],
        "loyalty_ledger": [
            {
                "entity_id": "e1",
                "ts": as_of,
                "direction": "burn",
                "value_minor": 200,
                "program_id": "default",
            },
            {
                "entity_id": "e2",
                "ts": as_of,
                "direction": "burn",
                "value_minor": 200,
                "program_id": "default",
            },
        ],
        "lifecycle": [
            {
                "entity_id": "e1",
                "created_at": "2025-01-01T00:00:00Z",
                "last_active_at": as_of,
            },
            {
                "entity_id": "e2",
                "created_at": "2025-01-01T00:00:00Z",
                "last_active_at": as_of,
            },
        ],
    }
    out = evaluate_loyalty_economics(
        entity_id="e1",
        feed_snapshot=snap,
        program_config=_cfg(),
        cluster_entity_ids=["e1", "e2"],
        now=now,
    )
    assert out["unit"] == "cluster"
    assert out["metrics"]["ltv_minor"] == 1000
    assert out["metrics"]["loyalty_cost_minor"] == 400
    assert out["metrics"]["loyalty_ltv_ratio"] == 0.4
