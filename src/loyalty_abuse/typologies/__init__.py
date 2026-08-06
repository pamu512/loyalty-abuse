from loyalty_abuse.typologies import (
    ato_redeem,
    bot_redeem,
    code_leak,
    gift_card_drain,
    multi_account,
    partner_promo_farm,
    promo_stack,
    referral_self_deal,
    return_to_points,
    trial_referral_farm,
)

ALL_SCORERS = [
    multi_account.score,
    referral_self_deal.score,
    promo_stack.score,
    bot_redeem.score,
    code_leak.score,
    ato_redeem.score,
    gift_card_drain.score,
    partner_promo_farm.score,
    return_to_points.score,
    trial_referral_farm.score,
]
