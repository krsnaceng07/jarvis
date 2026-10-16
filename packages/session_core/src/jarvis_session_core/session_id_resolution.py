"""Session-id resolution — fuzzy CLI/user input matching.

Mirrors OpenClaw's ``extensions/sessions/session-id-resolution.ts``:
resolves user-provided session references against the
session store while avoiding silent picks when multiple
plausible sessions tie.

The Python port keeps the same public surface:
- ``resolve_session_id_match_selection(matches, session_id)``
  → ``{kind: "none"} | {kind: "ambiguous", session_keys} |
       {kind: "selected", session_key}``
- ``resolve_preferred_session_key_for_session_id_matches(matches, session_id)``
  → ``str | None`` (the selected key, or ``None`` for
  none/ambiguous)

Selection contract (mirrors the TS source):
- Structural suffix/request-key matches beat fuzzy matches
- Tied structural matches stay ambiguous
- Tied fuzzy matches stay ambiguous
- Aliases that normalize to the same request key collapse
  to one (prefer freshest canonical key)

Python adaptations (documented in code):
- TS ``Map`` (insertion-ordered) → Python ``dict``
- TS ``toSorted`` (immutable sort) → Python ``sorted()``
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, Union

from .session_key_utils import to_agent_request_session_key

# ── Types ──────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class SessionEntry:
    """Minimal session entry — Python port uses a dict-like view.

    Mirrors the shape of the TS ``SessionEntry`` type but
    with a single ``updated_at_ms`` field (the only field
    this module reads). The host passes the actual store
    entries as dicts; we just need ``entry.get("updated_at")`` /
    ``entry.get("updatedAt")`` to work.
    """

    updated_at: int = 0

    @classmethod
    def from_dict(cls, entry: dict[str, Any]) -> "SessionEntry":
        """Build from a dict, accepting both snake_case and camelCase keys."""
        updated = entry.get("updated_at_ms")
        if updated is None:
            updated = entry.get("updatedAt") or entry.get("updated_at") or 0
        return cls(updated_at=int(updated))


@dataclass(frozen=True, slots=True)
class _NormalizedSessionIdMatch:
    session_key: str
    entry: SessionEntry
    normalized_session_key: str
    normalized_request_key: str
    is_canonical_session_key: bool
    is_structural: bool


# Discriminated union of selection results. Mirrors the TS
# ``SessionIdMatchSelection`` type.
SessionIdMatchSelection = Union[
    dict[str, Any],  # the three shapes are dicts to keep dict-typed portability
]


def _make_none() -> dict[str, Any]:
    return {"kind": "none"}


def _make_ambiguous(session_keys: list[str]) -> dict[str, Any]:
    return {"kind": "ambiguous", "session_keys": list(session_keys)}


def _make_selected(session_key: str) -> dict[str, Any]:
    return {"kind": "selected", "session_key": session_key}


# ── Sort helpers ───────────────────────────────────────────────────


def _compare_normalized_updated_at_descending(
    a: _NormalizedSessionIdMatch, b: _NormalizedSessionIdMatch
) -> int:
    """Sort by ``updated_at`` descending (freshest first)."""
    return (b.entry.updated_at or 0) - (a.entry.updated_at or 0)


def _compare_store_keys(a: str, b: str) -> int:
    if a < b:
        return -1
    if a > b:
        return 1
    return 0


# ── Normalize matches ─────────────────────────────────────────────


def _normalize_lowercase_string_or_empty(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip().lower()


def _normalize_session_id_matches(
    matches: list[tuple[str, dict[str, Any]]], normalized_session_id: str
) -> list[_NormalizedSessionIdMatch]:
    """Normalize session keys + classify each match as structural or fuzzy."""
    out: list[_NormalizedSessionIdMatch] = []
    for session_key, entry_dict in matches:
        normalized_session_key = _normalize_lowercase_string_or_empty(session_key)
        request_key = to_agent_request_session_key(session_key)
        normalized_request_key = _normalize_lowercase_string_or_empty(request_key or session_key)
        is_structural = (
            normalized_session_key.endswith(f":{normalized_session_id}")
            or normalized_request_key == normalized_session_id
            or normalized_request_key.endswith(f":{normalized_session_id}")
        )
        out.append(
            _NormalizedSessionIdMatch(
                session_key=session_key,
                entry=SessionEntry.from_dict(entry_dict),
                normalized_session_key=normalized_session_key,
                normalized_request_key=normalized_request_key,
                is_canonical_session_key=(session_key == normalized_session_key),
                is_structural=is_structural,
            )
        )
    return out


def _collapse_alias_matches(
    matches: list[_NormalizedSessionIdMatch],
) -> list[_NormalizedSessionIdMatch]:
    """Collapse aliases (same normalized request key) into a single match.

    Mirrors ``collapseAliasMatches``: for groups with
    multiple matches, prefer the freshest canonical key
    so ambiguity only reports distinct sessions.
    """
    grouped: dict[str, list[_NormalizedSessionIdMatch]] = {}
    for match in matches:
        grouped.setdefault(match.normalized_request_key, []).append(match)
    result: list[_NormalizedSessionIdMatch] = []
    for group in grouped.values():
        if len(group) == 1:
            result.append(group[0])
            continue
        sorted_group = sorted(
            group,
            key=lambda m: (
                -(m.entry.updated_at or 0),
                not m.is_canonical_session_key,
                m.normalized_session_key,
            ),
        )
        result.append(sorted_group[0])
    return result


def _select_freshest_unique_match(
    matches: list[_NormalizedSessionIdMatch],
) -> Optional[_NormalizedSessionIdMatch]:
    """Pick the freshest match if it's strictly newer than the runner-up.

    Returns ``None`` when two or more matches tie for
    freshness (caller should report ambiguous). Mirrors
    ``selectFreshestUniqueMatch``.
    """
    if len(matches) == 1:
        return matches[0]
    if not matches:
        return None
    sorted_matches = sorted(
        matches,
        key=lambda m: -(m.entry.updated_at or 0),
    )
    freshest = sorted_matches[0]
    second_freshest = sorted_matches[1] if len(sorted_matches) > 1 else None
    if second_freshest is None:
        return freshest
    if (freshest.entry.updated_at or 0) > (second_freshest.entry.updated_at or 0):
        return freshest
    return None


# ── Public surface ────────────────────────────────────────────────


def resolve_session_id_match_selection(
    matches: list[tuple[str, dict[str, Any]]], session_id: object
) -> dict[str, Any]:
    """Resolve a session-id match selection against store candidates.

    Mirrors ``resolveSessionIdMatchSelection``:
    - 0 matches → ``{kind: "none"}``
    - 1 canonical match → ``{kind: "selected", session_key}``
    - Multiple structural matches with a clear freshest →
      ``{kind: "selected", session_key}``
    - Multiple tied structural matches →
      ``{kind: "ambiguous", session_keys}``
    - Multiple canonical matches with a clear freshest →
      ``{kind: "selected", session_key}``
    - Tied canonical matches → ``{kind: "ambiguous", session_keys}``
    """
    if not matches:
        return _make_none()
    normalized_session_id = _normalize_lowercase_string_or_empty(session_id)
    canonical_matches = _collapse_alias_matches(
        _normalize_session_id_matches(matches, normalized_session_id)
    )
    if len(canonical_matches) == 1:
        return _make_selected(canonical_matches[0].session_key)
    structural_matches = [m for m in canonical_matches if m.is_structural]
    selected_structural = _select_freshest_unique_match(structural_matches)
    if selected_structural is not None:
        return _make_selected(selected_structural.session_key)
    if len(structural_matches) > 1:
        return _make_ambiguous([m.session_key for m in structural_matches])
    selected_canonical = _select_freshest_unique_match(canonical_matches)
    if selected_canonical is not None:
        return _make_selected(selected_canonical.session_key)
    return _make_ambiguous([m.session_key for m in canonical_matches])


def resolve_preferred_session_key_for_session_id_matches(
    matches: list[tuple[str, dict[str, Any]]], session_id: object
) -> Optional[str]:
    """Return the selected session key, or ``None`` for none/ambiguous.

    Mirrors ``resolvePreferredSessionKeyForSessionIdMatches``.
    """
    selection = resolve_session_id_match_selection(matches, session_id)
    if selection.get("kind") == "selected":
        return selection.get("session_key")
    return None


__all__ = [
    "SessionEntry",
    "SessionIdMatchSelection",
    "resolve_preferred_session_key_for_session_id_matches",
    "resolve_session_id_match_selection",
]
