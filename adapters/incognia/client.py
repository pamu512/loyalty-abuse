"""Fixture or live-gated Incognia fetch (never imported by core loyalty_abuse)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from adapters.incognia.normalize import IncogniaSignals, normalize_assessment

_FIXTURES = Path(__file__).resolve().parent / "fixtures"
_ENV_KEYS = (
    "INCOGNIA_CLIENT_ID",
    "INCOGNIA_CLIENT_SECRET",
    "INCOGNIA_POLICY_ID",
)
_DEFAULT_FIXTURE = "login_low_risk"


def env_creds_ready() -> bool:
    """True when all three Incognia env vars are non-empty."""
    return all(os.environ.get(k) for k in _ENV_KEYS)


def _unavailable() -> IncogniaSignals:
    return normalize_assessment({}, source="unavailable")


def _load_fixture(fixture_name: str) -> IncogniaSignals:
    name = fixture_name if fixture_name.endswith(".json") else f"{fixture_name}.json"
    path = _FIXTURES / name
    raw: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return normalize_assessment(raw, source="fixture")


def _live_assessment(
    *,
    request_token: str,
    account_id: str,
    event_type: str,
    external_id: str | None,
    policy_id: str,
) -> dict[str, Any]:
    from incognia.api import IncogniaAPI

    client_id = os.environ["INCOGNIA_CLIENT_ID"]
    client_secret = os.environ["INCOGNIA_CLIENT_SECRET"]
    api = IncogniaAPI(client_id, client_secret)

    # ponytail: signup → register_new_signup; all other event types → register_login
    if event_type == "signup":
        return api.register_new_signup(
            request_token,
            account_id=account_id,
            external_id=external_id,
            policy_id=policy_id,
        )
    return api.register_login(
        request_token,
        account_id,
        external_id,
        policy_id=policy_id,
    )


def fetch_signals(
    *,
    request_token: str,
    account_id: str,
    event_type: str,
    external_id: str | None = None,
    fixture_name: str | None = None,
) -> IncogniaSignals:
    """Live if env creds present and SDK importable; else load fixture (default login_low_risk).

    Direct/unit use may rely on the fixture fallback. The API production path must not
    call this without creds unless an explicit fixture flag is set on the payload.
    """
    if not env_creds_ready():
        return _load_fixture(fixture_name or _DEFAULT_FIXTURE)

    try:
        raw = _live_assessment(
            request_token=request_token,
            account_id=account_id,
            event_type=event_type,
            external_id=external_id,
            policy_id=os.environ["INCOGNIA_POLICY_ID"],
        )
        if not isinstance(raw, dict):
            return _unavailable()
        return normalize_assessment(raw, source="live")
    except Exception:
        # ImportError / timeout / 5xx / anything else → degrade, do not raise
        return _unavailable()
