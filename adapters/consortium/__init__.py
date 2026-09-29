"""Consortium badness lookup — fail-closed stub (no live feed)."""

from __future__ import annotations

STATUS_NOT_CONFIGURED = "not_configured"
REASON_MISSING_FEED = "missing_feed"


def lookup_badness(hashes: list[str]) -> dict[str, object]:
    """Never return silent {}. Missing credentials/feed is a typed reject.

    Live consortium is not shipped; callers must treat this as blocked, not clean.
    """
    _ = hashes
    return {
        "status": STATUS_NOT_CONFIGURED,
        "reason": REASON_MISSING_FEED,
        "blocked": True,
        "scores": {},
    }


__all__ = [
    "STATUS_NOT_CONFIGURED",
    "REASON_MISSING_FEED",
    "lookup_badness",
]
