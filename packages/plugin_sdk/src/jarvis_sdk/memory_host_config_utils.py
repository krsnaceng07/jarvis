"""jarvis_sdk.memory_host_config_utils — narrow agent config helpers.

OpenClaw parity: mirrors a subset of
``packages/memory-host-sdk/src/host/config-utils.ts``.
This module ports only the helpers used by
``memory_host_read_file``: ``resolve_memory_host_agent_workspace_dir``,
``resolve_memory_host_agent_context_limits``, and
``resolve_memory_host_search_path_config`` (plus the
``OpenClawConfig`` TypedDict shape).

Key port decisions:
- The OpenClaw source is large (~370 LOC); the Python port
  ships only the surface used by ``read_file`` — i.e. the
  three agent helpers + the config TypedDict. The rest
  (``resolveRememberAcrossConversations``,
  ``resolveMemoryHostUserPath``, etc.) is deferred to a
  later phase.
- Home / state-dir resolution mirrors the OpenClaw
  ``OPENCLAW_HOME`` / ``OPENCLAW_STATE_DIR`` env-var
  semantics via ``os.environ`` + ``os.path.expanduser``.
"""
from __future__ import annotations

import os
from typing import Any, TypedDict


#: Mirrors OpenClaw's ``DEFAULT_AGENT_ID = "main"``.
DEFAULT_AGENT_ID: str = "main"

#: Mirrors OpenClaw's ``NEW_STATE_DIRNAME``.
NEW_STATE_DIRNAME: str = ".openclaw"

#: Mirrors OpenClaw's ``LEGACY_STATE_DIRNAMES``.
LEGACY_STATE_DIRNAMES: tuple[str, ...] = (".clawdbot",)


class AgentContextLimitsConfig(TypedDict, total=False):
    memoryGetDefaultLines: int  # noqa: N815
    memoryGetMaxChars: int  # noqa: N815


class MemorySearchConfig(TypedDict, total=False):
    enabled: bool
    rememberAcrossConversations: bool  # noqa: N815
    extraPaths: list[str]  # noqa: N815


class AgentConfig(TypedDict, total=False):
    id: str
    default: bool
    workspace: str
    memorySearch: MemorySearchConfig  # noqa: N815
    contextLimits: AgentContextLimitsConfig  # noqa: N815


class OpenClawConfig(TypedDict, total=False):
    agents: dict[str, Any]  # ``defaults`` + ``list``
    memory: dict[str, Any]
    session: dict[str, Any]
    bindings: list[Any]


def _normalize_agent_id(value: str | None) -> str:
    """Normalize an agent id (trim + lowercase). Mirrors OpenClaw."""
    if not isinstance(value, str):
        return DEFAULT_AGENT_ID
    return value.strip().lower() or DEFAULT_AGENT_ID


def _normalize_optional_string(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    trimmed = value.strip()
    if not trimmed or trimmed == "undefined" or trimmed == "null":
        return None
    return trimmed


def _list_agent_entries(cfg: OpenClawConfig) -> list[AgentConfig]:
    agents = cfg.get("agents") if isinstance(cfg, dict) else None
    if not isinstance(agents, dict):
        return []
    raw_list = agents.get("list")
    if not isinstance(raw_list, list):
        return []
    return [entry for entry in raw_list if isinstance(entry, dict)]


def _resolve_default_agent_id(cfg: OpenClawConfig) -> str:
    entries = _list_agent_entries(cfg)
    if not entries:
        return DEFAULT_AGENT_ID
    chosen = next((entry.get("id") for entry in entries if entry.get("default")), None)
    if chosen is None and entries:
        chosen = entries[0].get("id")
    return _normalize_agent_id(chosen) if isinstance(chosen, str) else DEFAULT_AGENT_ID


def _resolve_agent_config(
    cfg: OpenClawConfig,
    agent_id: str,
) -> AgentConfig | None:
    aid = _normalize_agent_id(agent_id)
    for entry in _list_agent_entries(cfg):
        entry_id = _normalize_agent_id(entry.get("id")) if isinstance(entry.get("id"), str) else None
        if entry_id == aid:
            return entry
    return None


def _strip_null_bytes(value: str) -> str:
    return value.replace("\0", "")


def _resolve_required_home_dir(env: dict[str, str] | None = None) -> str:
    """Resolve the home dir, preferring env vars (mirrors OpenClaw)."""
    env = env if env is not None else dict(os.environ)
    for var in ("OPENCLAW_HOME", "HOME", "USERPROFILE"):
        value = _normalize_optional_string(env.get(var))
        if value:
            return os.path.abspath(value)
    return os.path.abspath(os.getcwd())


def _resolve_default_agent_workspace_dir(
    env: dict[str, str] | None = None,
) -> str:
    home = _resolve_required_home_dir(env)
    profile = _normalize_optional_string((env or os.environ).get("OPENCLAW_PROFILE"))
    if profile and profile.lower() != "default":
        return os.path.join(home, NEW_STATE_DIRNAME, f"workspace-{profile}")
    return os.path.join(home, NEW_STATE_DIRNAME, "workspace")


def resolve_memory_host_agent_workspace_dir(
    cfg: OpenClawConfig,
    agent_id: str,
    env: dict[str, str] | None = None,
) -> str:
    """Resolve the workspace directory for ``agent_id``.

    Mirrors OpenClaw's ``resolveMemoryHostAgentWorkspaceDir``.
    Falls back to the configured agent workspace, then to
    the default workspace, then to a per-agent
    ``workspace-<id>`` subdir of the state root.
    """
    aid = _normalize_agent_id(agent_id)
    env = env if env is not None else dict(os.environ)
    entry = _resolve_agent_config(cfg, aid)
    configured = _normalize_optional_string(entry.get("workspace")) if entry else None
    if configured:
        return _strip_null_bytes(os.path.abspath(configured))
    agents_block = cfg.get("agents") if isinstance(cfg, dict) else None
    defaults = agents_block.get("defaults") if isinstance(agents_block, dict) else None
    fallback = _normalize_optional_string(defaults.get("workspace")) if isinstance(defaults, dict) else None
    if aid == _resolve_default_agent_id(cfg):
        if fallback:
            return _strip_null_bytes(os.path.abspath(fallback))
        return _strip_null_bytes(_resolve_default_agent_workspace_dir(env))
    if fallback:
        return _strip_null_bytes(os.path.join(os.path.abspath(fallback), aid))
    state_dir = _resolve_state_dir(env)
    return _strip_null_bytes(os.path.join(state_dir, f"workspace-{aid}"))


def _resolve_state_dir(env: dict[str, str] | None = None) -> str:
    env = env if env is not None else dict(os.environ)
    override = _normalize_optional_string(env.get("OPENCLAW_STATE_DIR"))
    if override:
        return os.path.abspath(override)
    home = _resolve_required_home_dir(env)
    return os.path.join(home, NEW_STATE_DIRNAME)


def resolve_memory_host_agent_context_limits(
    cfg: OpenClawConfig | None,
    agent_id: str | None = None,
) -> AgentContextLimitsConfig | None:
    """Resolve context limits for an agent with defaults fallback.

    Mirrors OpenClaw's ``resolveMemoryHostAgentContextLimits``.
    """
    if not isinstance(cfg, dict):
        return None
    agents_block = cfg.get("agents") if isinstance(cfg, dict) else None
    defaults = agents_block.get("defaults") if isinstance(agents_block, dict) else None
    default_limits = defaults.get("contextLimits") if isinstance(defaults, dict) else None
    if not cfg or not agent_id:
        return default_limits if isinstance(default_limits, dict) else None
    entry = _resolve_agent_config(cfg, agent_id)
    if entry and isinstance(entry.get("contextLimits"), dict):
        return entry["contextLimits"]
    return default_limits if isinstance(default_limits, dict) else None


def _normalize_string_entries(values: list[str] | None) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values or []:
        if not isinstance(value, str):
            continue
        trimmed = value.strip()
        if not trimmed or trimmed in seen:
            continue
        seen.add(trimmed)
        out.append(trimmed)
    return out


def resolve_memory_host_search_path_config(
    cfg: OpenClawConfig,
    agent_id: str,
) -> dict[str, Any] | None:
    """Resolve the enabled search-path config for ``agent_id``.

    Mirrors OpenClaw's ``resolveMemoryHostSearchPathConfig``.
    Returns ``None`` when memory search is disabled; returns
    a ``{enabled, rememberAcrossConversations, extraPaths}``
    dict otherwise.
    """
    if not isinstance(cfg, dict):
        return None
    agents_block = cfg.get("agents")
    if not isinstance(agents_block, dict):
        return None
    defaults = agents_block.get("defaults")
    default_search = defaults.get("memorySearch") if isinstance(defaults, dict) else None
    entry = _resolve_agent_config(cfg, agent_id)
    override_search = entry.get("memorySearch") if entry else None
    enabled: bool = True
    if isinstance(override_search, dict) and "enabled" in override_search:
        enabled = bool(override_search["enabled"])
    elif isinstance(default_search, dict) and "enabled" in default_search:
        enabled = bool(default_search["enabled"])
    if not enabled:
        return None
    extra = _normalize_string_entries(
        [
            *(default_search.get("extraPaths", []) if isinstance(default_search, dict) else []),
            *(override_search.get("extraPaths", []) if isinstance(override_search, dict) else []),
        ]
    )
    return {
        "enabled": True,
        "rememberAcrossConversations": bool(
            (override_search.get("rememberAcrossConversations") if isinstance(override_search, dict) else None)
            or (default_search.get("rememberAcrossConversations") if isinstance(default_search, dict) else None)
            or False
        ),
        "extraPaths": extra,
    }


__all__ = [
    "DEFAULT_AGENT_ID",
    "NEW_STATE_DIRNAME",
    "LEGACY_STATE_DIRNAMES",
    "AgentConfig",
    "AgentContextLimitsConfig",
    "MemorySearchConfig",
    "OpenClawConfig",
    "resolve_memory_host_agent_workspace_dir",
    "resolve_memory_host_agent_context_limits",
    "resolve_memory_host_search_path_config",
]
