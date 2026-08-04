from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from loyalty_abuse.schema import EventEnvelope, EventType


def _parse_ts(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(timezone.utc)


def _email_root(email: str | None) -> str | None:
    if not email or "@" not in email:
        return None
    local, domain = email.lower().split("@", 1)
    local = local.split("+", 1)[0].replace(".", "")
    return f"{local}@{domain}"


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
        d24 = timedelta(hours=24)
        d5m = timedelta(minutes=5)
        on_device = self._in_window(now, d24, lambda e: e.device_id == event.device_id and e.tenant_id == event.tenant_id)
        on_ip = self._in_window(now, d24, lambda e: e.ip == event.ip and e.tenant_id == event.tenant_id)
        accounts_device = {e.account_id for e in on_device}
        accounts_ip = {e.account_id for e in on_ip}

        roots: dict[str, set[str]] = defaultdict(set)
        for e in self._in_window(now, d24, lambda e: e.tenant_id == event.tenant_id):
            root = _email_root(e.email)
            if root:
                roots[root].add(e.account_id)
        email_alias_burst = any(len(v) >= 3 for v in roots.values())

        referral_shared_device = False
        referral_shared_payment = False
        if event.type == EventType.referral:
            ref = str(event.payload.get("referrer_id") or "")
            ree = str(event.payload.get("referee_id") or event.account_id)
            devices = {}
            pays = {}
            for e in self._events:
                if e.tenant_id != event.tenant_id:
                    continue
                devices[e.account_id] = e.device_id
                if e.payment_instrument_hash:
                    pays[e.account_id] = e.payment_instrument_hash
            referral_shared_device = bool(ref and ree and devices.get(ref) and devices.get(ref) == devices.get(ree))
            referral_shared_payment = bool(ref and ree and pays.get(ref) and pays.get(ref) == pays.get(ree))

        offers = list(event.payload.get("offer_ids") or [])
        promos = list(event.payload.get("promo_codes") or [])
        loyalty = list(event.payload.get("loyalty_applied") or [])
        stack_depth = len(offers) + len(promos) + len(loyalty)
        discount_depth = float(event.payload.get("discount_pct") or 0)

        redeem_5m = self._in_window(
            now, d5m, lambda e: e.device_id == event.device_id and e.type == EventType.redeem
        )
        signup_5m = self._in_window(
            now, d5m, lambda e: e.device_id == event.device_id and e.type == EventType.signup
        )

        code = None
        if promos:
            code = str(promos[0])
        elif event.payload.get("referral_code"):
            code = str(event.payload["referral_code"])
        code_users: set[str] = set()
        if code:
            for e in self._in_window(now, d24, lambda e: e.tenant_id == event.tenant_id):
                plist = list(e.payload.get("promo_codes") or [])
                if code in plist or e.payload.get("referral_code") == code:
                    code_users.add(e.account_id)

        acct_events = [e for e in self._events if e.account_id == event.account_id and e.tenant_id == event.tenant_id]
        acct_events_sorted = sorted(acct_events, key=lambda e: _parse_ts(e.ts))
        signup_ts = next((_parse_ts(e.ts) for e in acct_events_sorted if e.type == EventType.signup), None)
        account_age_minutes = (now - signup_ts).total_seconds() / 60.0 if signup_ts else 0.0
        minutes_signup_to_event = account_age_minutes

        ato_chain = False
        minutes_login_to_redeem = None
        recent = [e for e in acct_events_sorted if _parse_ts(e.ts) <= now]
        for i, e in enumerate(recent):
            if e.type != EventType.login:
                continue
            if not (e.payload.get("new_device") or e.payload.get("geo")):
                continue
            login_t = _parse_ts(e.ts)
            prof = next(
                (
                    p
                    for p in recent[i + 1 :]
                    if p.type == EventType.profile_update and (_parse_ts(p.ts) - login_t) <= timedelta(minutes=30)
                ),
                None,
            )
            if not prof:
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
            if red or event.type in {EventType.redeem, EventType.checkout}:
                ato_chain = True
                minutes_login_to_redeem = (now - login_t).total_seconds() / 60.0
                break

        force_hard = ato_chain or len(redeem_5m) >= 20 or len(signup_5m) >= 15
        return {
            "accounts_on_device_24h": len(accounts_device),
            "accounts_on_ip_24h": len(accounts_ip),
            "email_alias_burst": email_alias_burst,
            "referral_shared_device": referral_shared_device,
            "referral_shared_payment": referral_shared_payment,
            "stack_depth": stack_depth,
            "discount_depth": discount_depth,
            "redeem_count_5m": len(redeem_5m),
            "signup_count_5m": len(signup_5m),
            "code_unique_users_24h": len(code_users),
            "account_age_minutes": account_age_minutes,
            "minutes_signup_to_event": minutes_signup_to_event,
            "ato_chain": ato_chain,
            "minutes_login_to_redeem": minutes_login_to_redeem,
            "force_hard_floor": force_hard,
        }
