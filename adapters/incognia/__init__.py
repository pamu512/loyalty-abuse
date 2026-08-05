"""Incognia device-intel adapter (fixture + live-gated; no core imports)."""

from adapters.incognia.client import env_creds_ready, fetch_signals
from adapters.incognia.normalize import IncogniaSignals, normalize_assessment

__all__ = [
    "IncogniaSignals",
    "normalize_assessment",
    "fetch_signals",
    "env_creds_ready",
]
