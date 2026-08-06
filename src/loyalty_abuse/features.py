from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from loyalty_abuse.calibration import load_calibration
from loyalty_abuse.device_intel import intel_force_hard_floor
from loyalty_abuse.graph import cluster_features
from loyalty_abuse.schema import EventEnvelope, EventType


def _parse_ts(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(timezone.utc)


def _hard_floor_thresholds() -> tuple[int, int]:
    floor = load_calibration().get("hard_floor") or {}
    try:
        redeem = int(floor.get("redeem_5m", 20))
    except (TypeError, ValueError):
        redeem = 20
    try:
        signup = int(floor.get("signup_5m", 15))
    except (TypeError, ValueError):
        signup = 15
    return redeem, signup


def _email_root(email: str | None) -> str | None:
    if not email or "@" not in email:
        return None
    local, domain = email.lower().split("@", 1)
    local = local.split("+", 1)[0].replace(".", "")
    return f"{local}@{domain}"


_SENSITIVE_PROFILE_FIELDS = frozenset(
    {"email", "phone", "payment", "payment_instrument", "password"}
)


def _sensitive_profile_update(payload: dict[str, Any]) -> bool:
    fields = payload.get("fields_changed") or []
    return any(str(f).lower() in _SENSITIVE_PROFILE_FIELDS for f in fields)


def _stack_tokens(payload: dict[str, Any]) -> set[str]:
    tokens: set[str] = set()
    for key in ("offer_ids", "promo_codes", "loyalty_applied"):
        for x in payload.get(key) or []:
            tokens.add(f"{key}:{x}")
    oid = payload.get("offer_id")
    if oid is not None and str(oid) != "":
        tokens.add(f"offer_ids:{oid}")
    return tokens


class FeatureStore:
    def __init__(self) -> None:
        self._events: list[EventEnvelope] = []

    def observe(self, event: EventEnvelope) -> None:
        self._events.append(event)

    def _in_window(self, now: datetime, window: timedelta, pred) -> list[EventEnvelope]:
        start = now - window
        out = []
        for e in self._events:
            et = _parse_ts(e.ts)
            if et < start or et > now:
                continue
            if pred(e):
                out.append(e)
        return out

    def snapshot(self, event: EventEnvelope) -> dict[str, Any]:
        now = _parse_ts(event.ts)
        d5m = timedelta(minutes=5)
        windows = {
            "1h": timedelta(hours=1),
            "24h": timedelta(hours=24),
            "7d": timedelta(days=7),
        }

        accounts_device: dict[str, int] = {}
        accounts_ip: dict[str, int] = {}
        code_users_n: dict[str, int] = {}
        email_burst: dict[str, bool] = {}

        discount_depth = float(event.payload.get("discount_pct") or 0)

        promos = list(event.payload.get("promo_codes") or [])
        code = None
        if promos:
            code = str(promos[0])
        elif event.payload.get("referral_code"):
            code = str(event.payload["referral_code"])

        current_root = _email_root(event.email)
        if current_root is None:
            # fall back to any email root seen for this account
            for e in self._events:
                if e.account_id == event.account_id and e.tenant_id == event.tenant_id:
                    current_root = _email_root(e.email)
                    if current_root:
                        break

        for label, window in windows.items():
            on_device = self._in_window(
                now,
                window,
                lambda e: e.device_id == event.device_id and e.tenant_id == event.tenant_id,
            )
            on_ip = self._in_window(
                now,
                window,
                lambda e: e.ip == event.ip and e.tenant_id == event.tenant_id,
            )
            accounts_device[label] = len({e.account_id for e in on_device})
            accounts_ip[label] = len({e.account_id for e in on_ip})

            roots: dict[str, set[str]] = defaultdict(set)
            for e in self._in_window(now, window, lambda e: e.tenant_id == event.tenant_id):
                root = _email_root(e.email)
                if root:
                    roots[root].add(e.account_id)
            email_burst[label] = bool(
                current_root and len(roots.get(current_root, set())) >= 3
            )

            code_users: set[str] = set()
            if code:
                for e in self._in_window(now, window, lambda e: e.tenant_id == event.tenant_id):
                    plist = list(e.payload.get("promo_codes") or [])
                    if code in plist or e.payload.get("referral_code") == code:
                        code_users.add(e.account_id)
            code_users_n[label] = len(code_users)

        referral_shared_device = False
        referral_shared_payment = False
        if event.type == EventType.referral:
            ref = str(event.payload.get("referrer_id") or "")
            ree = str(event.payload.get("referee_id") or event.account_id)
            devices: dict[str, set[str]] = defaultdict(set)
            pays: dict[str, set[str]] = defaultdict(set)
            for e in self._events:
                if e.tenant_id != event.tenant_id:
                    continue
                devices[e.account_id].add(e.device_id)
                if e.payment_instrument_hash:
                    pays[e.account_id].add(e.payment_instrument_hash)
            if ref and ree:
                referral_shared_device = bool(devices.get(ref, set()) & devices.get(ree, set()))
                referral_shared_payment = bool(pays.get(ref, set()) & pays.get(ree, set()))

        redeem_5m = self._in_window(
            now,
            d5m,
            lambda e: e.device_id == event.device_id
            and e.tenant_id == event.tenant_id
            and e.type == EventType.redeem,
        )
        signup_5m = self._in_window(
            now,
            d5m,
            lambda e: e.device_id == event.device_id
            and e.tenant_id == event.tenant_id
            and e.type == EventType.signup,
        )

        acct_events = [
            e
            for e in self._events
            if e.account_id == event.account_id and e.tenant_id == event.tenant_id
        ]
        acct_events_sorted = sorted(acct_events, key=lambda e: _parse_ts(e.ts))
        signup_ts = next(
            (_parse_ts(e.ts) for e in acct_events_sorted if e.type == EventType.signup),
            None,
        )
        account_age_minutes = (now - signup_ts).total_seconds() / 60.0 if signup_ts else 0.0
        minutes_signup_to_event = account_age_minutes

        # ponytail: union stack tokens over 7d so sequential enroll/redeem builds depth
        stack_tokens: set[str] = set()
        stack_start = now - timedelta(days=7)
        for e in acct_events_sorted:
            et = _parse_ts(e.ts)
            if et < stack_start or et > now:
                continue
            stack_tokens |= _stack_tokens(e.payload)
        stack_tokens |= _stack_tokens(event.payload)
        stack_depth = len(stack_tokens)

        ato_chain = False
        ato_known_device = False
        minutes_login_to_redeem = None
        recent = [e for e in acct_events_sorted if _parse_ts(e.ts) <= now]
        for i, e in enumerate(recent):
            if e.type != EventType.login:
                continue
            is_new = e.payload.get("new_device") is True or e.payload.get("new_geo") is True
            login_t = _parse_ts(e.ts)
            prof = next(
                (
                    p
                    for p in recent[i + 1 :]
                    if p.type == EventType.profile_update
                    and (_parse_ts(p.ts) - login_t) <= timedelta(minutes=30)
                ),
                None,
            )
            if not prof:
                continue
            # classic ATO: new_device|new_geo; known-device: sensitive profile fields only
            if not is_new and not _sensitive_profile_update(prof.payload):
                continue
            red = next(
                (
                    r
                    for r in recent
                    if r.type in {EventType.redeem, EventType.checkout}
                    and _parse_ts(r.ts) >= _parse_ts(prof.ts)
                    and (_parse_ts(r.ts) - login_t) <= timedelta(minutes=30)
                ),
                None,
            )
            current_redeem_in_chain = (
                event.type in {EventType.redeem, EventType.checkout}
                and now >= _parse_ts(prof.ts)
                and (now - login_t) <= timedelta(minutes=30)
            )
            if red or current_redeem_in_chain:
                ato_chain = True
                ato_known_device = not is_new
                minutes_login_to_redeem = (now - login_t).total_seconds() / 60.0
                break

        redeem_floor, signup_floor = _hard_floor_thresholds()
        payload = event.payload if isinstance(event.payload, dict) else {}
        device_intel = (
            dict(payload["device_intel"])
            if isinstance(payload.get("device_intel"), dict)
            else {}
        )
        # Classic ATO (new_device|new_geo) keeps hard floor. Known-device ATO
        # uses typology confidence + soft floor (floor.soft.ato_chain) so score
        # and friction stay aligned instead of score≈11 + hard_challenge + p=1.
        force_hard = (
            (ato_chain and not ato_known_device)
            or len(redeem_5m) >= redeem_floor
            or len(signup_5m) >= signup_floor
            or intel_force_hard_floor(payload)
        )
        tenant_events = [
            e
            for e in self._events
            if e.tenant_id == event.tenant_id and _parse_ts(e.ts) <= now
        ]
        graph = cluster_features(tenant_events, event.account_id, now)

        # --- v3 typology signals ---
        gift_load_burn_minutes = 1e9
        gift_instruments: set[str] = set()
        gift_load_event = False
        for e in acct_events_sorted:
            if e.tenant_id != event.tenant_id:
                continue
            pl = e.payload if isinstance(e.payload, dict) else {}
            if pl.get("gift_card_load") or pl.get("stored_value_load"):
                gift_load_event = True
                load_t = _parse_ts(e.ts)
                if event.type in {EventType.redeem, EventType.checkout}:
                    gift_load_burn_minutes = min(
                        gift_load_burn_minutes,
                        (now - load_t).total_seconds() / 60.0,
                    )
            if e.payment_instrument_hash and (
                pl.get("gift_card_load")
                or pl.get("stored_value_load")
                or e.type == EventType.redeem
            ):
                gift_instruments.add(e.payment_instrument_hash)
        if event.payment_instrument_hash:
            gift_instruments.add(event.payment_instrument_hash)

        partner_promo = False
        partner_code = None
        for c in list(event.payload.get("promo_codes") or []):
            cs = str(c)
            if cs.upper().startswith("PARTNER") or cs.upper().startswith("COBRAND"):
                partner_promo = True
                partner_code = cs
                break
        if event.payload.get("partner_promo"):
            partner_promo = True
            partner_code = partner_code or str(event.payload.get("partner_promo"))
        partner_accounts = 0
        if partner_code:
            users: set[str] = set()
            for e in self._in_window(
                now, timedelta(hours=24), lambda e: e.tenant_id == event.tenant_id
            ):
                codes = [str(x) for x in (e.payload.get("promo_codes") or [])]
                if partner_code in codes or e.payload.get("partner_promo") == partner_code:
                    users.add(e.account_id)
            partner_accounts = len(users)

        return_cycles = 0
        points_restored = False
        reburn = False
        for e in acct_events_sorted:
            if _parse_ts(e.ts) < now - timedelta(days=7) or _parse_ts(e.ts) > now:
                continue
            pl = e.payload if isinstance(e.payload, dict) else {}
            if pl.get("refund") or pl.get("cancel") or pl.get("points_restored"):
                if pl.get("points_restored") or pl.get("refund"):
                    points_restored = True
                    return_cycles += 1
            if points_restored and e.type == EventType.redeem and _parse_ts(e.ts) <= now:
                reburn = True
        if event.payload.get("points_restored"):
            points_restored = True
        if points_restored and event.type == EventType.redeem:
            reburn = True

        trial_cycles = 0
        welcome = bool(
            event.payload.get("welcome_offer")
            or "welcome" in [str(x).lower() for x in (event.payload.get("offer_ids") or [])]
        )
        for e in acct_events_sorted:
            if _parse_ts(e.ts) < now - timedelta(days=7):
                continue
            pl = e.payload if isinstance(e.payload, dict) else {}
            if e.type == EventType.referral or pl.get("welcome_offer") or pl.get("trial_claim"):
                trial_cycles += 1
            if e.type == EventType.signup and pl.get("referral_code"):
                trial_cycles += 1

        campaign_age_hours = float(event.payload.get("campaign_age_hours") or 0.0)

        return {
            "accounts_on_device_1h": accounts_device["1h"],
            "accounts_on_device_24h": accounts_device["24h"],
            "accounts_on_device_7d": accounts_device["7d"],
            "accounts_on_ip_1h": accounts_ip["1h"],
            "accounts_on_ip_24h": accounts_ip["24h"],
            "accounts_on_ip_7d": accounts_ip["7d"],
            "email_alias_burst_1h": email_burst["1h"],
            "email_alias_burst_24h": email_burst["24h"],
            "email_alias_burst_7d": email_burst["7d"],
            "email_alias_burst": email_burst["24h"],
            "referral_shared_device": referral_shared_device,
            "referral_shared_payment": referral_shared_payment,
            "stack_depth": stack_depth,
            "discount_depth": discount_depth,
            "redeem_count_5m": len(redeem_5m),
            "signup_count_5m": len(signup_5m),
            "code_unique_users_1h": code_users_n["1h"],
            "code_unique_users_24h": code_users_n["24h"],
            "code_unique_users_7d": code_users_n["7d"],
            "account_age_minutes": account_age_minutes,
            "minutes_signup_to_event": minutes_signup_to_event,
            "ato_chain": ato_chain,
            "ato_known_device": ato_known_device,
            "minutes_login_to_redeem": minutes_login_to_redeem,
            "force_hard_floor": force_hard,
            "device_intel": device_intel,
            "device_intel_force_block": payload.get("device_intel_force_block") is True,
            "graph_cluster_size": graph["graph_cluster_size"],
            "graph_multi_hop_accounts": graph["graph_multi_hop_accounts"],
            "graph_age_diversity_hours": graph["graph_age_diversity_hours"],
            "graph_shared_attr_rarity": graph["graph_shared_attr_rarity"],
            "graph_cluster_similarity": graph.get("graph_cluster_similarity", 0.0),
            "graph_ring_density": graph.get("graph_ring_density", 0.0),
            "gift_card_load_burn_minutes": gift_load_burn_minutes,
            "gift_card_instrument_churn": float(len(gift_instruments)),
            "gift_card_load_event": gift_load_event
            or bool(payload.get("gift_card_load") or payload.get("stored_value_load")),
            "partner_promo_code": partner_promo,
            "partner_code_accounts_24h": partner_accounts,
            "return_points_cycles_7d": return_cycles,
            "points_restored_after_refund": points_restored,
            "reburn_after_restore": reburn,
            "trial_referral_cycles_7d": trial_cycles,
            "welcome_offer_claimed": welcome,
            "promo_campaign_age_hours": campaign_age_hours,
            # Grab-style multi-bucket conquer aliases (same values; contract for cal/replay)
            "counter_accounts_device_5m": float(
                len(
                    {
                        e.account_id
                        for e in self._in_window(
                            now,
                            d5m,
                            lambda e: e.device_id == event.device_id
                            and e.tenant_id == event.tenant_id,
                        )
                    }
                )
            ),
            "counter_accounts_device_1h": float(accounts_device["1h"]),
            "counter_accounts_device_24h": float(accounts_device["24h"]),
            "counter_accounts_device_7d": float(accounts_device["7d"]),
        }
