"""jarvis.config.sessions — public facade for session store/lifecycle APIs.

OpenClaw parity: mirrors ``openclaw-main/src/config/sessions.ts``.

Focused minimal port: thin facade. The actual session subsystem lives
under ``src/agents/sessions/`` and is exposed through the
``embedded_agent_runner``/``agent_runtime`` runtime. The full re-export
of every ``sessions/*`` module lands as those subsystems are ported.
"""
from __future__ import annotations

# Re-export a few key types/values from the running session subsystem.
try:  # pragma: no cover
    from src.agents.sessions.session_key import normalize_session_key  # type: ignore
except Exception:  # pragma: no cover
    normalize_session_key = None  # type: ignore[assignment]


# Light-weight facade placeholders for the public surface.
def canonicalize_session_entry_aliases(*args, **kwargs):  # pragma: no cover
    raise NotImplementedError("canonicalizeSessionEntryAliases facade — install via runtime hooks")


def delete_session_entry_lifecycle(*args, **kwargs):  # pragma: no cover
    raise NotImplementedError("deleteSessionEntryLifecycle facade — install via runtime hooks")


def patch_session_entry_with_key(*args, **kwargs):  # pragma: no cover
    raise NotImplementedError("patchSessionEntryWithKey facade — install via runtime hooks")


def reset_session_entry_lifecycle(*args, **kwargs):  # pragma: no cover
    raise NotImplementedError("resetSessionEntryLifecycle facade — install via runtime hooks")


def resolve_session_entry_candidate_target(*args, **kwargs):  # pragma: no cover
    raise NotImplementedError("resolveSessionEntryCandidateTarget facade")


__all__ = [
    "canonicalize_session_entry_aliases",
    "delete_session_entry_lifecycle",
    "patch_session_entry_with_key",
    "reset_session_entry_lifecycle",
    "resolve_session_entry_candidate_target",
]
