from loyalty_abuse.typologies import (
    ato_redeem,
    bot_redeem,
    code_leak,
    multi_account,
    promo_stack,
    referral_self_deal,
)

ALL_SCORERS = [
    multi_account.score,
    referral_self_deal.score,
    promo_stack.score,
    bot_redeem.score,
    code_leak.score,
    ato_redeem.score,
]
