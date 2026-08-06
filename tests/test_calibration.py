import json

import pytest

from loyalty_abuse.calibration import CalibrationError, load_calibration
import loyalty_abuse.calibration as calibration_mod


def test_weights_sum_to_one():
    cal = load_calibration()
    total = sum(cal["weights"].values())
    assert abs(total - 1.0) < 1e-6


def test_policy_version():
    cal = load_calibration()
    assert cal["policy_version"] == "friction_v2_4"
    assert isinstance(cal["interactions"], list)
    assert isinstance(cal["soft_floors"], list)
    assert cal["blend"] == "weighted_sum"
    assert cal["cost"]["C_fn_per_usd"] == 1.0
    assert cal["cost"]["C_fp"]["block"] == 1.5
    assert cal["cost"]["miss_fraction"]["allow"] == 1.0


def test_missing_interactions_raises(tmp_path, monkeypatch):
    data = json.loads(calibration_mod._CAL_PATH.read_text())
    data.pop("interactions", None)
    path = tmp_path / "cal.json"
    path.write_text(json.dumps(data))
    monkeypatch.setattr(calibration_mod, "_CAL_PATH", path)
    load_calibration.cache_clear()
    with pytest.raises(CalibrationError):
        load_calibration()
    load_calibration.cache_clear()
