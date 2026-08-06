"""Unit tests for v3 typologies."""

from loyalty_abuse.typologies import (
    gift_card_drain,
    partner_promo_farm,
    return_to_points,
    trial_referral_farm,
)


def test_gift_card_drain_fires_on_fast_load_burn():
    r = gift_card_drain.score(
        {
            "gift_card_load_burn_minutes": 5,
            "gift_card_instrument_churn": 3,
            "gift_card_load_event": True,
        }
    )
    assert r.confidence > 0.3
    assert any(x.startswith("gift_card.") for x in r.reasons)


def test_partner_promo_farm_fires():
    r = partner_promo_farm.score(
        {
            "partner_promo_code": True,
            "partner_code_accounts_24h": 8,
            "accounts_on_device_24h": 6,
        }
    )
    assert r.confidence > 0.3
    assert any(x.startswith("partner_promo.") for x in r.reasons)


def test_return_to_points_fires():
    r = return_to_points.score(
        {
            "return_points_cycles_7d": 3,
            "points_restored_after_refund": True,
            "reburn_after_restore": True,
        }
    )
    assert r.confidence > 0.3


def test_trial_referral_farm_fires():
    r = trial_referral_farm.score(
        {
            "trial_referral_cycles_7d": 4,
            "welcome_offer_claimed": True,
            "accounts_on_device_24h": 5,
        }
    )
    assert r.confidence > 0.3
