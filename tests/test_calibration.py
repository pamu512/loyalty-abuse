from loyalty_abuse.calibration import load_calibration


def test_weights_sum_to_one():
    cal = load_calibration()
    total = sum(cal["weights"].values())
    assert abs(total - 1.0) < 1e-6


def test_policy_version():
    cal = load_calibration()
    assert cal["policy_version"] == "friction_v1_2"
    assert cal["blend"] == "weighted_sum"
