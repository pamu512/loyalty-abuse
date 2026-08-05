from datetime import datetime, timezone
import random

from loyalty_abuse.calibration import load_calibration
from loyalty_abuse.eval.adversarial import (
    GENERATORS,
    N_PER_SLICE,
    SLICE_BOUNDS,
    _geq,
    _score_journey,
    run_suite,
)
from loyalty_abuse.schema import FrictionAction


def test_adversarial_suite_passes():
    report = run_suite(seed=42)
    assert report["gates_pass"] is True


def test_catch_slices_not_velocity_hard_floor_vanity():
    """Caught slow_multi / sequential_promo journeys must not be redeem_5m hard_floor vanity."""
    load_calibration.cache_clear()
    cal = load_calibration()
    redeem_floor = int((cal.get("hard_floor") or {}).get("redeem_5m", 20))
    base = datetime(2026, 8, 5, 12, 0, 0, tzinfo=timezone.utc)
    rng = random.Random(42)

    checks = {
        "slow_multi_acct": "multi_acct.",
        "sequential_promo": "promo.",
    }
    for name, family in checks.items():
        gen = GENERATORS[name]
        for j in range(N_PER_SLICE):
            jr = random.Random(rng.randint(0, 2**31 - 1))
            d = _score_journey(gen(j, jr, base))
            if not _geq(d.friction, FrictionAction.soft_challenge):
                continue
            snap = d.features_snapshot
            redeem_5m = int(snap.get("redeem_count_5m") or 0)
            has_family = any(r.startswith(family) for r in d.reasons)
            # anti-vanity: not solely hard_floor; pattern family must fire with redeem under floor
            assert snap.get("force_hard_floor") is False or (
                has_family and redeem_5m < redeem_floor
            ), f"{name}[{j}] vanity hard_floor catch"
            assert has_family, f"{name}[{j}] missing {family}* reasons"
            assert redeem_5m < redeem_floor, f"{name}[{j}] redeem_5m={redeem_5m} >= floor"
            assert snap.get("force_hard_floor") is False, f"{name}[{j}] force_hard_floor set"


def test_slice_bounds_not_weakened():
    assert SLICE_BOUNDS["household_fp"]["bound"] >= 0.85
    assert SLICE_BOUNDS["device_rotation"]["bound"] >= 0.60
    assert SLICE_BOUNDS["slow_multi_acct"]["bound"] >= 0.70
    assert SLICE_BOUNDS["sequential_promo"]["bound"] >= 0.50
    assert SLICE_BOUNDS["ato_known_device"]["bound"] >= 0.50
