"""State-database path helpers.

Mirrors OpenClaw's ``src/state/openclaw-state-db.paths.ts``.
The Python port focuses on the two helpers the runtime
actually calls:

- ``resolve_state_sqlite_dir(env)`` — directory that holds
  the shared state SQLite file
- ``resolve_state_sqlite_path(env)`` — full path to the
  shared state SQLite file

Tests / dev workflows may override via the ``JARVIS_STATE_DIR``
environment variable. The Python port is a bit simpler than
the TS port because we do not need a worker-scoped temp
state root (pytest already isolates by tmp_path).
"""
from __future__ import annotations

import os
from typing import Optional


def resolve_state_root_dir(env: Optional[dict[str, str]] = None) -> str:
    """Resolve the JARVIS state root directory.

    Honors ``JARVIS_STATE_DIR`` if set + non-empty. Falls
    back to ``~/.jarvis/state``.

    The TS port branches on ``VITEST`` / ``NODE_ENV=test``
    to put each worker in a separate temp dir; the Python
    port relies on ``tmp_path`` instead (pytest is
    per-test isolated, not per-worker).
    """
    env = env or os.environ
    state_dir = (env.get("JARVIS_STATE_DIR") or "").strip()
    if state_dir:
        return os.path.abspath(state_dir)
    return os.path.join(os.path.expanduser("~"), ".jarvis", "state")


def resolve_state_sqlite_dir(env: Optional[dict[str, str]] = None) -> str:
    """Resolve the directory containing the shared state SQLite file.

    Mirrors ``resolveOpenClawStateSqliteDir``.
    """
    return resolve_state_root_dir(env)


def resolve_state_sqlite_path(env: Optional[dict[str, str]] = None) -> str:
    """Resolve the shared state SQLite file path.

    Mirrors ``resolveOpenClawStateSqlitePath``. Default
    filename is ``jarvis.sqlite``.
    """
    return os.path.join(resolve_state_sqlite_dir(env), "jarvis.sqlite")


def resolve_agent_sqlite_dir(agent_id: str, env: Optional[dict[str, str]] = None) -> str:
    """Resolve the per-agent database directory.

    Mirrors the OpenClaw path layout:
    ``<state-root>/../agents/<agent_id>/agent/``.

    In practice the agent DB sits under
    ``~/.jarvis/agents/<id>/agent.sqlite`` (matches our
    existing convention from Phase 5.14b). The TS port uses
    ``<state-dir>/../agents/<id>/agent/openclaw-agent.sqlite``;
    the Python port normalizes both into the same on-disk
    location.
    """
    agent_id = agent_id.strip()
    if not agent_id:
        raise ValueError("agent_id must be a non-empty string")
    return os.path.join(
        os.path.dirname(resolve_state_sqlite_dir(env)),
        "agents",
        agent_id,
    )


def resolve_agent_sqlite_path(agent_id: str, env: Optional[dict[str, str]] = None) -> str:
    """Resolve the per-agent SQLite file path.

    Mirrors ``resolveOpenClawAgentSqlitePath``. Default
    filename is ``agent.sqlite``.
    """
    return os.path.join(resolve_agent_sqlite_dir(agent_id, env), "agent.sqlite")


__all__ = [
    "resolve_agent_sqlite_dir",
    "resolve_agent_sqlite_path",
    "resolve_state_root_dir",
    "resolve_state_sqlite_dir",
    "resolve_state_sqlite_path",
]
