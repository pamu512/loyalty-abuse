from loyalty_abuse.eval.adversarial import run_suite


def test_adversarial_suite_passes():
    report = run_suite(seed=42)
    assert report["gates_pass"] is True
