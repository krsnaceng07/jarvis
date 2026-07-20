"""jarvis_sdk.agent_runtime — agent scope + workspace resolution.

OpenClaw parity: mirrors ``openclaw/plugin-sdk/agent-runtime``'s
``resolveAgentDir`` / ``resolveAgentWorkspaceDir`` /
``resolveDefaultAgentId`` / ``resolveSessionAgentId``.

Used by ``memory-core`` to locate per-agent data directories
(``~/.jarvis/agents/<id>/``) and to map session keys back to
the agent that owns them.

Architecture
============
In OpenClaw the agent resolution chain is:
  config.agents.defaults -> config.agents.list -> first entry
  -> "default".

The Python port follows the same chain. ``resolve_default_agent_id``
returns the agent id from the user's config (or "default"
when no agents are configured). ``resolve_agent_dir`` joins
that id with the host's data dir.

Parity
======
- ``resolve_default_agent_id(config)`` → ``str``
- ``resolve_agent_dir(config, agent_id)`` → ``str``
- ``resolve_agent_workspace_dir(config, agent_id)`` → ``str``
- ``resolve_session_agent_id(...)`` → ``str``
"""

from __future__ import annotations

import os
from pathlib import Path

from .routing import normalize_agent_id

DEFAULT_AGENT_ID = "default"


def resolve_default_agent_id(config: dict | None) -> str:
    """Resolve the default agent id from a config dict.

    Mirrors OpenClaw's ``resolveDefaultAgentId``. Returns
    ``"default"`` when no agent is configured (the JARVIS
    single-agent default).
    """
    if not config:
        return DEFAULT_AGENT_ID
    agents = config.get("agents") if isinstance(config, dict) else None
    if not agents:
        return DEFAULT_AGENT_ID
    defaults = agents.get("defaults") if isinstance(agents, dict) else None
    if isinstance(defaults, dict) and isinstance(defaults.get("id"), str):
        return normalize_agent_id(defaults["id"])
    listing = agents.get("list") if isinstance(agents, dict) else None
    if isinstance(listing, list) and listing:
        first = listing[0]
        if isinstance(first, dict) and isinstance(first.get("id"), str):
            return normalize_agent_id(first["id"])
    return DEFAULT_AGENT_ID


def _data_dir() -> Path:
    env = os.environ.get("JARVIS_DATA_DIR")
    if env:
        return Path(env).expanduser()
    return Path.home() / ".jarvis"


def resolve_agent_dir(config: dict | None, agent_id: str) -> str:
    """Return the per-agent data dir for ``agent_id``.

    Mirrors ``openclaw/plugin-sdk/agent-runtime``'s
    ``resolveAgentDir``.
    """
    canonical = normalize_agent_id(agent_id)
    return str(_data_dir() / "agents" / canonical)


def resolve_agent_workspace_dir(config: dict | None, agent_id: str) -> str:
    """Return the per-agent workspace dir for ``agent_id``.

    Mirrors ``openclaw/plugin-sdk/agent-runtime``'s
    ``resolveAgentWorkspaceDir``. JARVIS workspaces live at
    ``~/.jarvis/agents/<id>/workspace/`` so the same files
    (config, memory, skills) are co-located.
    """
    canonical = normalize_agent_id(agent_id)
    return str(_data_dir() / "agents" / canonical / "workspace")


def resolve_session_agent_id(
    config: dict | None,
    session_key: str | None = None,
    agent_id: str | None = None,
) -> str:
    """Resolve the agent id that owns a session.

    Mirrors ``openclaw/plugin-sdk/agent-runtime``'s
    ``resolveSessionAgentId``. If an explicit ``agent_id`` is
    passed, normalize and return it. Otherwise inspect
    ``session_key`` (OpenClaw encodes agent as
    ``agent:<id>:...``). Otherwise fall back to the default
    agent id.
    """
    if agent_id:
        return normalize_agent_id(agent_id)
    if not session_key:
        return resolve_default_agent_id(config)
    # OpenClaw convention: "agent:<id>:<rest>" → agent id = <id>
    if session_key.startswith("agent:"):
        tail = session_key[len("agent:") :]
        candidate = tail.split(":", 1)[0] if tail and ":" in tail else tail
        if candidate and candidate != "*":
            return normalize_agent_id(candidate)
    return resolve_default_agent_id(config)


__all__ = [
    "DEFAULT_AGENT_ID",
    "resolve_agent_dir",
    "resolve_agent_workspace_dir",
    "resolve_default_agent_id",
    "resolve_session_agent_id",
]
