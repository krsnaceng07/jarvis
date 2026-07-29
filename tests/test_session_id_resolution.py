"""Tests for src/sessions/session_id_resolution.py.

Mirrors OpenClaw's ``extensions/sessions/session-id-resolution.test.ts``.
"""
from __future__ import annotations

import pytest

from src.sessions.session_id_resolution import (
    resolve_preferred_session_key_for_session_id_matches,
    resolve_session_id_match_selection,
)


def _entry(updated_at: int = 0) -> dict:
    return {"updated_at_ms": updated_at}


# ── resolve_session_id_match_selection ──────────────────────────


class TestResolveSessionIdMatchSelection:
    def test_no_matches(self) -> None:
        result = resolve_session_id_match_selection([], "abc")
        assert result == {"kind": "none"}

    def test_single_canonical_match(self) -> None:
        """One match → selected."""
        matches = [("agent:1:discord:channel:abc", _entry())]
        result = resolve_session_id_match_selection(matches, "abc")
        assert result == {
            "kind": "selected",
            "session_key": "agent:1:discord:channel:abc",
        }

    def test_structural_suffix_match(self) -> None:
        """A session key ending in ``:abc`` is a structural match."""
        matches = [
            ("agent:1:discord:channel:abc", _entry()),
            ("agent:1:discord:channel:def", _entry()),
        ]
        result = resolve_session_id_match_selection(matches, "abc")
        # The one with ``:abc`` suffix is structural; the
        # other isn't. Single structural match → selected.
        assert result == {
            "kind": "selected",
            "session_key": "agent:1:discord:channel:abc",
        }

    def test_structural_match_freshest(self) -> None:
        """Multiple structural matches: pick the freshest."""
        matches = [
            ("agent:1:discord:channel:abc", _entry(100)),
            ("agent:1:telegram:group:abc", _entry(200)),
        ]
        result = resolve_session_id_match_selection(matches, "abc")
        assert result == {
            "kind": "selected",
            "session_key": "agent:1:telegram:group:abc",
        }

    def test_structural_match_tie_is_ambiguous(self) -> None:
        """Tied structural matches (same updated_at) → ambiguous."""
        matches = [
            ("agent:1:discord:channel:abc", _entry(100)),
            ("agent:1:telegram:group:abc", _entry(100)),
        ]
        result = resolve_session_id_match_selection(matches, "abc")
        assert result["kind"] == "ambiguous"
        assert set(result["session_keys"]) == {
            "agent:1:discord:channel:abc",
            "agent:1:telegram:group:abc",
        }

    def test_fuzzy_match_freshest(self) -> None:
        """When no structural match: pick the freshest fuzzy match."""
        matches = [
            ("agent:1:discord:channel:abc", _entry(100)),
            ("agent:1:discord:channel:def", _entry(200)),
        ]
        # The session_id is "xyz" — neither key ends with :xyz
        # → both are fuzzy matches.
        result = resolve_session_id_match_selection(matches, "xyz")
        assert result == {
            "kind": "selected",
            "session_key": "agent:1:discord:channel:def",
        }

    def test_fuzzy_match_tie_is_ambiguous(self) -> None:
        """Tied fuzzy matches → ambiguous."""
        matches = [
            ("agent:1:discord:channel:abc", _entry(100)),
            ("agent:1:discord:channel:def", _entry(100)),
        ]
        result = resolve_session_id_match_selection(matches, "xyz")
        assert result["kind"] == "ambiguous"
        assert len(result["session_keys"]) == 2

    def test_aliases_collapse(self) -> None:
        """Aliases that normalize to the same request key collapse."""
        from routing.session_key import to_agent_request_session_key
        # Two keys that map to the same agent request key
        matches = [
            ("agent:1:discord:channel:abc", _entry(100)),
            ("agent:1:discord:channel:abc-legacy", _entry(50)),
        ]
        # Both should map to the same canonical form
        canonical = to_agent_request_session_key("agent:1:discord:channel:abc")
        assert canonical is not None
        result = resolve_session_id_match_selection(matches, canonical.split(":")[-1])
        # The freshest alias wins (100 vs 50)
        assert result["kind"] == "selected"
        assert result["session_key"] == "agent:1:discord:channel:abc"

    def test_structural_beats_fuzzy(self) -> None:
        """A structural match wins over multiple fuzzy matches."""
        matches = [
            ("agent:1:discord:channel:abc", _entry(50)),  # structural for "abc"
            ("agent:1:discord:channel:def", _entry(200)),  # fuzzy
            ("agent:1:discord:channel:ghi", _entry(300)),  # fuzzy
        ]
        result = resolve_session_id_match_selection(matches, "abc")
        # Structural match selected despite lower updated_at
        assert result == {
            "kind": "selected",
            "session_key": "agent:1:discord:channel:abc",
        }

    def test_empty_session_id(self) -> None:
        """Empty session_id: structural match won't match (no suffix)."""
        matches = [
            ("agent:1:discord:channel:abc", _entry(100)),
            ("agent:1:discord:channel:def", _entry(200)),
        ]
        result = resolve_session_id_match_selection(matches, "")
        # No structural matches (empty suffix), fuzzy ties → ambiguous
        # Actually, : ends with :"" would match all. Let me check.
        # normalized_session_id = "", isStructural: endsWith(":" + "")
        # which is endsWith(":") for any key with a trailing colon.
        # For "agent:1:discord:channel:abc" — doesn't end with ":"
        # For "agent:1:discord:channel:def" — doesn't end with ":"
        # So no structural match. Two fuzzy matches, freshest
        # is def (200). Result: selected def.
        assert result["kind"] == "selected"
        assert result["session_key"] == "agent:1:discord:channel:def"


# ── resolve_preferred_session_key_for_session_id_matches ──────────


class TestResolvePreferredSessionKeyForSessionIdMatches:
    def test_returns_selected_key(self) -> None:
        matches = [("agent:1:discord:channel:abc", _entry())]
        assert (
            resolve_preferred_session_key_for_session_id_matches(matches, "abc")
            == "agent:1:discord:channel:abc"
        )

    def test_returns_none_for_no_matches(self) -> None:
        assert (
            resolve_preferred_session_key_for_session_id_matches([], "abc") is None
        )

    def test_returns_none_for_ambiguous(self) -> None:
        matches = [
            ("agent:1:discord:channel:abc", _entry(100)),
            ("agent:1:telegram:group:abc", _entry(100)),
        ]
        # Tied structural matches → ambiguous → None
        assert (
            resolve_preferred_session_key_for_session_id_matches(matches, "abc")
            is None
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
