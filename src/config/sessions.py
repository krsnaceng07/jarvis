"""jarvis.config.sessions — public facade for session store/lifecycle APIs.

OpenClaw parity: mirrors ``openclaw-main/src/config/sessions.ts``.

Focused minimal port: thin facade. The actual session subsystem lives
under ``src/agents/sessions/`` and is exposed through the
``embedded_agent_runner``/``agent_runtime`` runtime. The full re-export
of every ``sessions/*`` module lands as those subsystems are ported.
"""

from __future__ import annotations

from typing import Any

from src.config.io import get_installed_runtime_hook

# Re-export a few key types/values from the running session subsystem.
try:  # pragma: no cover
    from src.agents.sessions.session_key import normalize_session_key  # type: ignore
except Exception:  # pragma: no cover
    normalize_session_key = None  # type: ignore[assignment]


def _call_session_runtime_hook(name: str, *args: Any, **kwargs: Any):
    """Invoke an installed runtime hook for the session facade.

    Mirrors the config IO facade pattern: caller-installed runtime hooks take
    precedence, and a NotImplementedError remains the fail-closed default when
    no authoritative runtime implementation exists.
    """
    hook = get_installed_runtime_hook(name)
    if callable(hook):
        return hook(*args, **kwargs)
    raise NotImplementedError(f"{name} facade — install via runtime hooks")


def canonicalize_session_entry_aliases(*args, **kwargs):  # pragma: no cover
    return _call_session_runtime_hook("canonicalize_session_entry_aliases", *args, **kwargs)


def delete_session_entry_lifecycle(*args, **kwargs):  # pragma: no cover
    return _call_session_runtime_hook("delete_session_entry_lifecycle", *args, **kwargs)


def patch_session_entry_with_key(*args, **kwargs):  # pragma: no cover
    return _call_session_runtime_hook("patch_session_entry_with_key", *args, **kwargs)


def reset_session_entry_lifecycle(*args, **kwargs):  # pragma: no cover
    return _call_session_runtime_hook("reset_session_entry_lifecycle", *args, **kwargs)


def resolve_session_entry_candidate_target(*args, **kwargs):  # pragma: no cover
    return _call_session_runtime_hook("resolve_session_entry_candidate_target", *args, **kwargs)


__all__ = [
    "canonicalize_session_entry_aliases",
    "delete_session_entry_lifecycle",
    "patch_session_entry_with_key",
    "reset_session_entry_lifecycle",
    "resolve_session_entry_candidate_target",
]
