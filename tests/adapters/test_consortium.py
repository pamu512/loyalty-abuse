"""Consortium adapter: typed missing-feed stub, never silent {}."""

from __future__ import annotations


def test_lookup_badness_returns_typed_missing_feed():
    from adapters.consortium import lookup_badness

    for hashes in ([], ["abc", "def"]):
        result = lookup_badness(hashes)
        assert result != {}
        assert result.get("status") == "not_configured"
        assert result.get("reason") == "missing_feed"
        assert result.get("blocked") is True
        assert result.get("scores") == {}
