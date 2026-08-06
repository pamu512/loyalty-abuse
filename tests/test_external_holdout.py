"""Frozen external journey pack — independent of generator loop at eval time."""

from pathlib import Path

from loyalty_abuse.eval.external_holdout import load_pack, run_external_holdout

PACK = Path(__file__).parent / "fixtures" / "external_journeys.json"


def test_external_pack_is_frozen_events():
    pack = load_pack(PACK)
    assert len(pack) >= 6
    for j in pack:
        assert j["events"], j["id"]
        assert "expect" in j
        # Must not require live generator call — events are the source of truth.
        assert "frozen_from" in j


def test_external_holdout_passes():
    report = run_external_holdout(PACK)
    assert report["gates_pass"] is True, report
    assert report["failures"] == 0
    assert report["source"] == "frozen_external_pack"


def test_household_external_not_extreme_p():
    report = run_external_holdout(PACK)
    hh = [j for j in report["journeys"] if j["label"] == "household_fp"]
    assert hh
    assert all(j["p_abuse"] <= 0.55 for j in hh)
