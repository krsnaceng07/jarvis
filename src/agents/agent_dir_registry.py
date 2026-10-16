"""jarvis.agents.agent_dir_registry — process-local agentDir → agentId reverse registry.

OpenClaw parity: mirrors ``src/agents/agent-dir-registry.ts``.

The registry maps resolved (absolute, canonical) agent directories back to the
agent id that was prepared for them. It is populated by ``resolve_agent_dir``
at agent-preparation time and used by any runtime path that starts with an
already-prepared ``agentDir`` and needs to recover the owning agent's id
without re-reading config.

Architecture note: this is a process-local module-level dict — no persistence,
no file I/O. The registry resets on every process start. Mirrors OpenClaw's
module-level ``const agentIdByDir = new Map<string, string>()``.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Process-local registry
# ---------------------------------------------------------------------------

# Resolved absolute agentDir (canonical form) → normalized agentId.
# Module-level so it survives the entire process lifetime.
_agent_id_by_dir: dict[str, str] = {}


def _normalize_agent_dir_key(agent_dir: str, env: dict[str, str] | None = None) -> str:
    """Produce a stable lookup key from *agent_dir*.

    Mirrors ``normalizeAgentDirKey``:
    - Expand ``~`` using the env HOME (or os.path.expanduser fallback).
    - Resolve to an absolute path.
    - On Windows/macOS lowercase for case-insensitive filesystems.
    """
    effective_env = env if env is not None else dict(os.environ)
    # Tilde expansion respecting env HOME/USERPROFILE.
    if agent_dir.startswith("~"):
        home = effective_env.get("HOME") or effective_env.get("USERPROFILE") or str(Path.home())
        if agent_dir == "~":
            agent_dir = home
        elif agent_dir.startswith("~/") or agent_dir.startswith("~\\"):
            agent_dir = os.path.join(home, agent_dir[2:])
    resolved = os.path.abspath(agent_dir)
    if sys.platform in ("darwin", "win32"):
        return resolved.lower()
    return resolved


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def register_resolved_agent_dir(
    agent_id: str,
    agent_dir: str,
    *,
    env: dict[str, str] | None = None,
) -> None:
    """Register *agent_dir* for later reverse lookup to *agent_id*.

    Mirrors ``registerResolvedAgentDir``.

    Parameters
    ----------
    agent_id:
        Normalized agent id.
    agent_dir:
        The resolved agent directory path.
    env:
        Optional env dict for ``~`` expansion (defaults to ``os.environ``).
    """
    key = _normalize_agent_dir_key(agent_dir, env)
    _agent_id_by_dir[key] = agent_id


def resolve_registered_agent_id_for_dir(
    agent_dir: str,
    *,
    env: dict[str, str] | None = None,
) -> str | None:
    """Return the agent id registered for *agent_dir*, or ``None``.

    Mirrors ``resolveRegisteredAgentIdForDir``.
    """
    key = _normalize_agent_dir_key(agent_dir, env)
    return _agent_id_by_dir.get(key)


def clear_agent_dir_registry() -> None:
    """Clear the registry (test / process-reset helper).

    Not part of the OpenClaw public surface — used in tests to reset
    module state between runs.
    """
    _agent_id_by_dir.clear()


__all__ = [
    "register_resolved_agent_dir",
    "resolve_registered_agent_id_for_dir",
    "clear_agent_dir_registry",
]
