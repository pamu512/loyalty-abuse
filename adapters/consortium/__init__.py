"""Consortium badness lookup (no-op stub)."""

from __future__ import annotations


def lookup_badness(hashes: list[str]) -> dict[str, float]:
    """Return per-hash badness scores. Stub always returns {}."""
    _ = hashes
    return {}


__all__ = ["lookup_badness"]
