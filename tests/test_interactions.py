from loyalty_abuse.calibration import load_calibration
from loyalty_abuse.interactions import blend_raw, interaction_results
from loyalty_abuse.mathutil import clip


def test_multi_promo_full_confidence_scores_68():
    cal = load_calibration()
    weights = cal["weights"]
    interactions = cal["interactions"]
    conf = {
        "ato_redeem": 0.0,
        "multi_account": 1.0,
        "bot_redeem": 0.0,
        "referral_self_deal": 0.0,
        "code_leak": 0.0,
        "promo_stack": 1.0,
    }
    raw = blend_raw(weights, conf, interactions)
    # w_multi + w_promo + α_multi_promo = 0.28 + 0.18 + 0.22
    assert abs(raw - 0.68) < 1e-12
    assert int(round(100.0 * clip(raw))) == 68

    rows = interaction_results(conf, interactions)
    ix = next(r for r in rows if r.id == "ix.multi_promo")
    assert ix.points == 22
    assert abs(ix.confidence - 1.0) < 1e-12
    assert sum(r.points for r in rows if r.points > 0) == 22
