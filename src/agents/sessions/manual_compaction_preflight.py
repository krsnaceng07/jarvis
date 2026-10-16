"""jarvis.agents.sessions.manual_compaction_preflight — manual compaction preflight.

OpenClaw parity: mirrors
``openclaw-main/src/agents/sessions/manual-compaction-preflight.ts``.

Public surface (matches the OpenClaw
source):

- :func:`preflight_manual_session_compaction` —
  plan a manual compaction without
  aborting or otherwise mutating
  the active session. Returns either
  ``{"compactable": True,
  "preparation": ...}`` or
  ``{"compactable": False, "reason":
  ...}``. Mirrors
  :func:`preflightManualSessionCompaction`
  (``manual-compaction-preflight.ts:13-41``).

Phase 6.13a — focused port.

Adaptations
-----------
- The OpenClaw source's
  :func:`prepareCompaction` comes
  from
  ``@openclaw/agent-core/src/harness/compaction/compaction.js``.
  The Python port's runtime lands
  in 6.13+; this module ships the
  focused minimal port that mirrors
  the OpenClaw semantics (returns
  ``"Already compacted"`` when the
  last entry is a compaction, or
  ``"Nothing to compact (session
  too small)"`` when there's not
  enough history).
- The OpenClaw source's
  :class:`CompactionPreparation` +
  :class:`CompactionSettings` types
  come from the same runtime. The
  Python port uses plain ``dict``
  at runtime (the typed shape lands
  in 6.13+).
- The OpenClaw source's
  :class:`SessionEntry` type lives
  in :mod:`session-manager.ts`. The
  Python port uses plain ``dict``
  at runtime.
"""
from __future__ import annotations

import logging
from typing import Any


_LOG = logging.getLogger(
    "jarvis.agents.sessions.manual_compaction_preflight"
)


#: A manual-compaction preflight
#: result. Mirrors
#: :class:`ManualCompactionPreflight`
#: (``manual-compaction-preflight.ts:8-10``).
#: The Python port uses a plain dict.
ManualCompactionPreflight = dict


#: Threshold (in entries) below which
#: a session is considered "too
#: small" to compact. Mirrors the
#: OpenClaw source's behaviour: a
#: manual compaction needs at least
#: one message + the recent-keep
#: window. The Python port uses 2
#: (a user message + a target).
_MIN_PATH_ENTRIES_FOR_COMPACTION = 2


def _is_compaction_entry(entry: Any) -> bool:
    """Return ``True`` when ``entry`` is
    a compaction entry. Mirrors the
    OpenClaw source's
    ``entry.type === "compaction"``
    check.
    """
    if isinstance(entry, dict):
        return entry.get("type") == "compaction"
    return getattr(entry, "type", None) == "compaction"


def _build_preparation(
    path_entries: list, settings: dict
) -> dict:
    """Build a :class:`CompactionPreparation`
    for the supplied path entries.
    Mirrors the OpenClaw source's
    :func:`prepareCompaction` call
    (the focused minimal port)."""
    keep_recent_tokens = settings.get("keepRecentTokens", 20000)
    # Phase 6.13a — STUB. The full
    # ``prepareCompaction`` runtime
    # lands in 6.13+; for now, the
    # preparation just bundles the
    # path entries + the keep-recent
    # budget.
    return {
        "pathEntries": list(path_entries),
        "keepRecentTokens": keep_recent_tokens,
        "settings": dict(settings),
    }


def preflight_manual_session_compaction(
    path_entries: list,
    settings: dict,
) -> ManualCompactionPreflight:
    """Plan a manual compaction without
    aborting or otherwise mutating
    the active session. Mirrors
    :func:`preflightManualSessionCompaction`
    (``manual-compaction-preflight.ts:13-41``).

    The OpenClaw source first calls
    :func:`prepareCompaction` with
    the configured settings; when that
    returns ``None`` (the session
    fits the keep budget), it retries
    with ``keepRecentTokens: 0`` (the
    smallest valid history). The
    Python port follows the same
    shape.

    Parameters
    ----------
    path_entries : list
        The current branch entries
        (``session_manager.getBranch()``).
    settings : dict
        Compaction settings
        (``settings_manager.getCompactionSettings()``).

    Returns
    -------
    dict
        ``{"compactable": True,
        "preparation": dict}`` on
        success, or
        ``{"compactable": False,
        "reason": str}`` when the
        session is too small / already
        compacted.
    """
    if not path_entries:
        return {
            "compactable": False,
            "reason": "Nothing to compact (session too small)",
        }
    if len(path_entries) < _MIN_PATH_ENTRIES_FOR_COMPACTION:
        return {
            "compactable": False,
            "reason": "Nothing to compact (session too small)",
        }
    # Last entry is a compaction →
    # already compacted.
    if _is_compaction_entry(path_entries[-1]):
        return {
            "compactable": False,
            "reason": "Already compacted",
        }
    # Build the preparation (the
    # OpenClaw source's
    # ``prepareCompaction(...)``
    # call). The Python port's
    # focused minimal implementation
    # returns a dict.
    preparation = _build_preparation(path_entries, settings)
    return {
        "compactable": True,
        "preparation": preparation,
    }


# ============================================================================
# Backwards-compat alias (camelCase
# OpenClaw-style name).
# ============================================================================


preflightManualSessionCompaction = (
    preflight_manual_session_compaction
)


__all__ = [
    "ManualCompactionPreflight",
    "preflight_manual_session_compaction",
    "preflightManualSessionCompaction",
]
