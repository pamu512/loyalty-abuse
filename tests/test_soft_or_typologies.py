from __future__ import annotations

from loyalty_abuse.calibration import load_calibration, sat_params
from loyalty_abuse.mathutil import sat, soft_or
from loyalty_abuse.typologies import (
    bot_redeem,
    code_leak,
    multi_account,
    promo_stack,
    referral_self_deal,
)


def test_multi_account_soft_or_not_max():
    snap = {
        "accounts_on_device_1h": 0,
        "accounts_on_device_24h": 4,
        "accounts_on_device_7d": 4,
        "accounts_on_ip_1h": 0,
        "accounts_on_ip_24h": 0,
        "accounts_on_ip_7d": 0,
        "email_alias_burst": True,
        "email_alias_burst_24h": True,
        "account_age_minutes": 120,
    }
    cal = load_calibration()
    c_dev = soft_or(
        [
            sat(float(snap["accounts_on_device_1h"]), *sat_params("accounts_on_device_1h")),
            sat(float(snap["accounts_on_device_24h"]), *sat_params("accounts_on_device_24h")),
            sat(float(snap["accounts_on_device_7d"]), *sat_params("accounts_on_device_7d")),
        ]
    )
    c_ip = soft_or(
        [
            sat(float(snap["accounts_on_ip_1h"]), *sat_params("accounts_on_ip_1h")),
            sat(float(snap["accounts_on_ip_24h"]), *sat_params("accounts_on_ip_24h")),
            sat(float(snap["accounts_on_ip_7d"]), *sat_params("accounts_on_ip_7d")),
        ]
    )
    c_email = float(cal.get("email_burst_confidence") or 0.75)
    c_graph = sat(float(snap.get("graph_cluster_size") or 0), *sat_params("graph_cluster_size"))
    expected = soft_or([c_dev, c_ip, c_email, c_graph])
    r = multi_account.score(snap)
    assert r.confidence == expected
    assert r.confidence > max(c_dev, c_ip, c_email, c_graph)
    assert r.confidence > 0.75


def test_promo_stack_soft_or():
    snap = {"stack_depth": 4, "discount_depth": 50}
    c_stack = sat(4.0, *sat_params("stack_depth"))
    c_disc = sat(50.0, *sat_params("discount_depth"))
    expected = soft_or([c_stack, c_disc])
    r = promo_stack.score(snap)
    assert r.confidence == expected
    assert r.confidence > max(c_stack, c_disc)


def test_bot_redeem_soft_or_then_young():
    snap = {
        "redeem_count_5m": 8,
        "signup_count_5m": 6,
        "account_age_minutes": 30,
    }
    cal = load_calibration()
    c_r = sat(8.0, *sat_params("redeem_count_5m"))
    c_s = sat(6.0, *sat_params("signup_count_5m"))
    base = soft_or([c_r, c_s])
    expected = min(1.0, base * float(cal.get("young_bot_mult") or 1.15))
    r = bot_redeem.score(snap)
    assert r.confidence == expected
    assert base > max(c_r, c_s)


def test_code_leak_soft_or_windows():
    snap = {
        "code_unique_users_1h": 20,
        "code_unique_users_24h": 30,
        "code_unique_users_7d": 40,
    }
    expected = soft_or(
        [
            sat(20.0, *sat_params("code_unique_users_1h")),
            sat(30.0, *sat_params("code_unique_users_24h")),
            sat(40.0, *sat_params("code_unique_users_7d")),
        ]
    )
    r = code_leak.score(snap)
    assert r.confidence == expected


def test_referral_both_uses_both_c():
    cal = load_calibration()
    r = referral_self_deal.score(
        {"referral_shared_device": True, "referral_shared_payment": True}
    )
    assert r.confidence == float(cal.get("referral_both_c") or 1.0)


def test_referral_single_channel_soft_or():
    cal = load_calibration()
    c_d = float(cal.get("referral_shared_device_c") or 0.9)
    r = referral_self_deal.score(
        {"referral_shared_device": True, "referral_shared_payment": False}
    )
    assert r.confidence == soft_or([c_d])
