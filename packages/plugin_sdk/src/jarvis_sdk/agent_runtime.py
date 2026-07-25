"""jarvis_sdk.agent_runtime — agent scope + workspace + model resolution.

OpenClaw parity: mirrors ``openclaw/plugin-sdk/agent-runtime``'s
``resolveAgentDir``, ``resolveAgentWorkspaceDir``,
``resolveDefaultAgentId``, ``resolveSessionAgentId``,
``resolveAgentEffectiveModelPrimary``,
``resolveDefaultModelForAgent``, ``parseModelRef``,
``DEFAULT_PROVIDER``, and ``resolveRememberAcrossConversations``.

Used by ``memory-core``, ``memory-lancedb``, and
``active-memory`` to locate per-agent data directories, map
session keys back to agents, resolve the active model in
the chain ``plugin.model → session model → agent primary →
plugin.modelFallback``, and to read the per-agent
``rememberAcrossConversations`` flag.

Architecture
============
In OpenClaw the agent resolution chain is:
  config.agents.defaults -> config.agents.list -> first entry
  -> "default".

The Python port follows the same chain. ``resolve_default_agent_id``
returns the agent id from the user's config (or "default"
when no agents are configured). ``resolve_agent_dir`` joins
that id with the host's data dir.

``resolve_agent_effective_model_primary`` returns the agent's
configured primary model (provider/model). ``parse_model_ref``
splits a "provider/model" string into a tuple. ``resolve_default_model_for_agent``
walks the agent config to find the most-specific model. The
``resolve_remember_across_conversations`` helper reads the
per-agent flag that active-memory uses to enable private
transcript recall.

Parity
======
- ``resolve_default_agent_id(config)`` → ``str``
- ``resolve_agent_dir(config, agent_id)`` → ``str``
- ``resolve_agent_workspace_dir(config, agent_id)`` → ``str``
- ``resolve_session_agent_id(...)`` → ``str``
- ``resolve_agent_effective_model_primary(config, agent_id)`` → ``str | None``
- ``resolve_default_model_for_agent(params)`` → ``dict | None``
- ``parse_model_ref(ref, default_provider)`` → ``dict | None``
- ``resolve_remember_across_conversations(config, agent_id)`` → ``bool``
- ``DEFAULT_PROVIDER`` is ``"openai"`` (matches OpenClaw).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from routing.routing import normalize_agent_id

DEFAULT_AGENT_ID = "default"
DEFAULT_PROVIDER = "openai"


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


def resolve_agent_config(config: Any, agent_id: str) -> dict[str, Any] | None:
    """Return the agent's full config entry from ``config.agents``.

    Mirrors OpenClaw's ``resolveAgentConfig``. Returns the
    agent entry (``config.agents.<id>`` or
    ``config.agents.list[i]`` matching the id) or ``None``
    if the agent is not configured. The returned dict is
    the live config object — callers should not mutate it.
    """
    if not isinstance(config, dict):
        return None
    canonical = normalize_agent_id(agent_id)
    # Direct lookup: config["agents"][id]
    agents_section = config.get("agents")
    if isinstance(agents_section, dict):
        entry = agents_section.get(canonical)
        if isinstance(entry, dict):
            return entry
    # List lookup: config["agents"]["list"][i]
    if isinstance(agents_section, dict):
        list_section = agents_section.get("list")
        if isinstance(list_section, list):
            for item in list_section:
                if isinstance(item, dict) and normalize_agent_id(item.get("id")) == canonical:
                    return item
    return None


def resolve_store_path(
    configured_store: Any,
    options: dict[str, Any] | None = None,
) -> str:
    """Resolve the session store path.

    Mirrors OpenClaw's ``resolveStorePath``. Returns the
    configured store path or a default under
    ``<data_dir>/sessions.json`` when the configured value
    is empty / unset. ``options.agentId`` is reserved for
    per-agent overrides (currently unused in the default
    fallback).
    """
    if isinstance(configured_store, str) and configured_store.strip():
        return configured_store.strip()
    return str(_data_dir() / "sessions.json")


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


def _agent_entry(config: Any, agent_id: str) -> dict[str, Any] | None:
    if not isinstance(config, dict):
        return None
    agents = config.get("agents")
    if not isinstance(agents, dict):
        return None
    listing = agents.get("list")
    if not isinstance(listing, list):
        return None
    canonical = normalize_agent_id(agent_id)
    for entry in listing:
        if not isinstance(entry, dict):
            continue
        if isinstance(entry.get("id"), str) and normalize_agent_id(entry["id"]) == canonical:
            return entry
    return None


def resolve_agent_effective_model_primary(
    config: Any,
    agent_id: str,
) -> str | None:
    """Return the agent's configured primary model ``provider/model``.

    Mirrors OpenClaw's ``resolveAgentEffectiveModelPrimary``.
    Returns ``None`` when the agent has no primary model
    configured. The string follows the OpenClaw convention
    ``<provider>/<model>`` (or just ``<model>`` when the
    default provider applies).
    """
    entry = _agent_entry(config, agent_id)
    if not isinstance(entry, dict):
        return None
    primary = entry.get("model")
    if not isinstance(primary, dict):
        return None
    provider = primary.get("provider")
    model = primary.get("model")
    if isinstance(model, str) and model.strip():
        if isinstance(provider, str) and provider.strip():
            return f"{provider.strip()}/{model.strip()}"
        return model.strip()
    return None


def resolve_default_model_for_agent(params: dict[str, Any]) -> dict[str, str] | None:
    """Resolve the default model for an agent.

    Mirrors OpenClaw's ``resolveDefaultModelForAgent``. Walks
    ``config.agents.list[].model.{primary,latest,fallback}``
    in priority order; returns a dict with ``provider`` and
    ``model`` (or ``None`` if no default is set).
    """
    cfg = params.get("cfg")
    agent_id = params.get("agentId")
    if not isinstance(cfg, dict) or not isinstance(agent_id, str):
        return None
    entry = _agent_entry(cfg, agent_id)
    if not isinstance(entry, dict):
        return None
    model_section = entry.get("model")
    if not isinstance(model_section, dict):
        return None
    for key in ("primary", "latest", "fallback"):
        candidate = model_section.get(key)
        if not isinstance(candidate, dict):
            continue
        provider = candidate.get("provider")
        model = candidate.get("model")
        if isinstance(model, str) and model.strip():
            return {
                "provider": provider.strip()
                if isinstance(provider, str) and provider.strip()
                else DEFAULT_PROVIDER,
                "model": model.strip(),
            }
    return None


def parse_model_ref(
    model_ref: str | None,
    default_provider: str = DEFAULT_PROVIDER,
) -> dict[str, str] | None:
    """Parse a ``provider/model`` string into a dict.

    Mirrors OpenClaw's ``parseModelRef``. Returns ``None``
    for empty / non-string input. When no provider prefix is
    present, ``default_provider`` is used.
    """
    if not isinstance(model_ref, str):
        return None
    trimmed = model_ref.strip()
    if not trimmed:
        return None
    if "/" in trimmed:
        provider, model = trimmed.split("/", 1)
        if provider.strip() and model.strip():
            return {"provider": provider.strip(), "model": model.strip()}
    return {"provider": default_provider, "model": trimmed}


def resolve_remember_across_conversations(
    config: Any,
    agent_id: str,
) -> bool:
    """Return whether ``agent_id`` has ``rememberAcrossConversations``.

    Mirrors OpenClaw's ``resolveRememberAcrossConversations``.
    Reads the agent entry from ``config.agents.list[]`` and
    returns the boolean flag. Defaults to ``False`` when the
    agent has no entry.
    """
    entry = _agent_entry(config, agent_id)
    if not isinstance(entry, dict):
        return False
    flag = entry.get("rememberAcrossConversations")
    return isinstance(flag, bool) and flag is True


__all__ = [
    "DEFAULT_AGENT_ID",
    "DEFAULT_PROVIDER",
    "parse_model_ref",
    "resolve_agent_dir",
    "resolve_agent_effective_model_primary",
    "resolve_agent_workspace_dir",
    "resolve_default_agent_id",
    "resolve_default_model_for_agent",
    "resolve_remember_across_conversations",
    "resolve_session_agent_id",
]
