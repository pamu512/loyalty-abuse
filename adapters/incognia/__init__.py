"""Incognia device-intel adapter (fixture + live-gated; no core imports)."""

from adapters.incognia.normalize import IncogniaSignals, normalize_assessment

__all__ = ["IncogniaSignals", "normalize_assessment"]
