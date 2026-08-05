"""Consortium adapter: no-op badness lookup."""

from __future__ import annotations


def test_lookup_badness_returns_empty_dict():
    from adapters.consortium import lookup_badness

    assert lookup_badness([]) == {}
    assert lookup_badness(["abc", "def"]) == {}
