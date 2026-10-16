"""jarvis.agents.agent_scope_config — agent config resolution.

OpenClaw parity: mirrors ``src/agents/agent-scope-config.ts``.

Pure config-reading module — no filesystem I/O except path resolution via
``os.path``. All functions accept a Jarvis config dict and return normalized
values.

Key exports
-----------
- ``list_agent_entries(cfg)`` — raw valid entries.
- ``list_agent_ids(cfg)`` — deduplicated normalized ids.
- ``resolve_default_agent_id(cfg)`` — single canonical default.
- ``resolve_agent_config(cfg, agent_id)`` → ``ResolvedAgentConfig | None``.
- ``resolve_agent_workspace_dir(cfg, agent_id)`` — resolved workspace path.
- ``resolve_agent_dir(cfg, agent_id)`` — resolved agentDir path; registers in
  the process-local dir registry as a side-effect (matches TS behavior).
- ``resolve_default_agent_dir(cfg)`` — shorthand for the default agent.
- ``resolve_agent_context_limits(cfg, agent_id)`` — merged context limits.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from .agent_dir_registry import register_resolved_agent_dir

_log = logging.getLogger("jarvis.agents.agent_scope_config")

DEFAULT_AGENT_ID = "main"

# Warn once when multiple agents are marked default=True.
_default_agent_warned = False


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _strip_null_bytes(s: str) -> str:
    """Strip null bytes from paths to prevent ENOTDIR errors.

    Mirrors ``stripNullBytes``.
    """
    return s.replace("\0", "")


def _resolve_user_path(path: str, env: dict[str, str] | None = None) -> str:
    """Expand ``~`` and resolve to an absolute path.

    Mirrors ``resolveUserPath`` from OpenClaw utils.
    """
    effective = env if env is not None else dict(os.environ)
    if path.startswith("~"):
        home = effective.get("HOME") or effective.get("USERPROFILE") or str(__import__("pathlib").Path.home())
        if path == "~":
            path = home
        elif path.startswith("~/") or path.startswith("~\\"):
            path = os.path.join(home, path[2:])
    return os.path.abspath(path)


def _resolve_state_dir(env: dict[str, str] | None = None) -> str:
    """Resolve the Jarvis state directory.

    Mirrors ``resolveStateDir``:
    JARVIS_STATE_DIR → OPENCLAW_STATE_DIR → ~/.jarvis
    """
    effective = env if env is not None else dict(os.environ)
    state = effective.get("JARVIS_STATE_DIR") or effective.get("OPENCLAW_STATE_DIR")
    if state:
        return _resolve_user_path(state, effective)
    home = effective.get("HOME") or effective.get("USERPROFILE") or str(__import__("pathlib").Path.home())
    return os.path.join(home, ".jarvis")


def _resolve_default_agent_workspace_dir(env: dict[str, str] | None = None) -> str:
    """Resolve the default agent workspace directory.

    Mirrors ``resolveDefaultAgentWorkspaceDir``:
    OPENCLAW_WORKSPACE_DIR → <stateDir>/workspace
    """
    effective = env if env is not None else dict(os.environ)
    override = effective.get("JARVIS_WORKSPACE_DIR") or effective.get("OPENCLAW_WORKSPACE_DIR")
    if override:
        return _resolve_user_path(override, effective)
    return os.path.join(_resolve_state_dir(effective), "workspace")


def _normalize_agent_id(value: object) -> str:
    """Normalize an agent id. Raises ``ValueError`` on invalid inputs."""
    from src.routing.agent_id import normalize_agent_id  # noqa: PLC0415
    return normalize_agent_id(value)


def _read_string_value(value: object) -> str | None:
    """Return *value* as a non-empty stripped string or None."""
    if isinstance(value, str):
        stripped = value.strip()
        return stripped if stripped else None
    return None


def _has_explicit_model_policy_allow(model_policy: object) -> bool:
    """Return True when the modelPolicy has an explicit allow list.

    Mirrors ``hasExplicitModelPolicyAllow``.
    """
    if not isinstance(model_policy, dict):
        return False
    allow = model_policy.get("allow")
    return isinstance(allow, list) and len(allow) > 0


# ---------------------------------------------------------------------------
# Core list / lookup
# ---------------------------------------------------------------------------


def list_agent_entries(cfg: dict[str, Any]) -> list[dict[str, Any]]:
    """List valid configured agent entries from config.

    Mirrors ``listAgentEntries``.
    """
    agents = cfg.get("agents") if isinstance(cfg, dict) else None
    if not isinstance(agents, dict):
        return []
    lst = agents.get("list")
    if not isinstance(lst, list):
        return []
    return [e for e in lst if isinstance(e, dict)]


def list_agent_ids(cfg: dict[str, Any]) -> list[str]:
    """List unique normalized agent ids.

    Mirrors ``listAgentIds``: falls back to ``["main"]`` when no agents
    are configured.
    """
    agents = list_agent_entries(cfg)
    if not agents:
        return [DEFAULT_AGENT_ID]
    seen: set[str] = set()
    ids: list[str] = []
    for entry in agents:
        try:
            aid = _normalize_agent_id(entry.get("id"))
        except ValueError:
            continue
        if aid not in seen:
            seen.add(aid)
            ids.append(aid)
    return ids if ids else [DEFAULT_AGENT_ID]


def resolve_default_agent_id(cfg: dict[str, Any]) -> str:
    """Resolve the default agent id.

    Mirrors ``resolveDefaultAgentId``:
    1. First entry with ``default: true``.
    2. First entry.
    3. Hardcoded ``"main"``.

    Warns once when multiple entries have ``default: true``.
    """
    global _default_agent_warned
    agents = list_agent_entries(cfg)
    if not agents:
        return DEFAULT_AGENT_ID
    defaults = [a for a in agents if a.get("default")]
    if len(defaults) > 1 and not _default_agent_warned:
        _default_agent_warned = True
        _log.warning(
            "Multiple agents marked default=true; using the first entry as default."
        )
    chosen = (defaults[0] if defaults else agents[0]).get("id", "")
    try:
        return _normalize_agent_id((chosen or "").strip() or DEFAULT_AGENT_ID)
    except ValueError:
        return DEFAULT_AGENT_ID


def _resolve_agent_entry(cfg: dict[str, Any], agent_id: str) -> dict[str, Any] | None:
    """Find the config entry for *agent_id* (normalized)."""
    nid = _normalize_agent_id(agent_id)
    for entry in list_agent_entries(cfg):
        try:
            if _normalize_agent_id(entry.get("id", "")) == nid:
                return entry
        except ValueError:
            continue
    return None


# ---------------------------------------------------------------------------
# Resolved config
# ---------------------------------------------------------------------------


def resolve_agent_config(
    cfg: dict[str, Any],
    agent_id: str,
) -> dict[str, Any] | None:
    """Return the merged per-agent config for *agent_id*.

    Mirrors ``resolveAgentConfig``. Returns ``None`` when the agent is
    not configured. Merges ``agents.defaults`` into the per-agent entry
    where entries are undefined.
    """
    entry = _resolve_agent_entry(cfg, agent_id)
    if entry is None:
        return None
    defaults: dict[str, Any] = {}
    agents_block = cfg.get("agents")
    if isinstance(agents_block, dict):
        raw_defaults = agents_block.get("defaults")
        if isinstance(raw_defaults, dict):
            defaults = raw_defaults

    # model: string or dict; else None.
    model = entry.get("model")
    if not (isinstance(model, str) or (isinstance(model, dict) and model)):
        model = None

    # experimental: merge defaults then entry.
    experimental_default = defaults.get("experimental") if defaults else None
    experimental_entry = entry.get("experimental")
    if isinstance(experimental_entry, dict) and experimental_entry:
        experimental = {**(experimental_default or {}), **experimental_entry}
    else:
        experimental = experimental_default or None

    # contextLimits: merge defaults then entry.
    cl_default = defaults.get("contextLimits")
    cl_entry = entry.get("contextLimits")
    if isinstance(cl_entry, dict) and cl_entry:
        context_limits = {**(cl_default or {}), **cl_entry}
    elif isinstance(cl_default, dict) and cl_default:
        context_limits = cl_default
    else:
        context_limits = None

    # runRetries: merge defaults then entry.
    rr_default = defaults.get("runRetries")
    rr_entry = entry.get("runRetries")
    if isinstance(rr_entry, dict) and rr_entry:
        run_retries = {**(rr_default or {}), **rr_entry}
    elif isinstance(rr_default, dict) and rr_default:
        run_retries = rr_default
    else:
        run_retries = None

    result: dict[str, Any] = {
        "name": _read_string_value(entry.get("name")),
        "workspace": _read_string_value(entry.get("workspace")),
        "agentDir": _read_string_value(entry.get("agentDir")),
        "model": model,
        "utilityModel": _read_string_value(entry.get("utilityModel")),
        "thinkingDefault": entry.get("thinkingDefault"),
        "verboseDefault": entry.get("verboseDefault") or defaults.get("verboseDefault"),
        "reasoningDefault": entry.get("reasoningDefault"),
        "fastModeDefault": entry.get("fastModeDefault"),
        "contextTokens": entry.get("contextTokens") or defaults.get("contextTokens"),
        "contextInjection": entry.get("contextInjection"),
        "bootstrapMaxChars": entry.get("bootstrapMaxChars"),
        "bootstrapTotalMaxChars": entry.get("bootstrapTotalMaxChars"),
        "experimental": experimental,
        "skills": entry.get("skills") if isinstance(entry.get("skills"), list) else None,
        "memorySearch": entry.get("memorySearch"),
        "humanDelay": entry.get("humanDelay"),
        "tts": entry.get("tts"),
        "contextLimits": context_limits,
        "heartbeat": entry.get("heartbeat"),
        "identity": entry.get("identity"),
        "groupChat": entry.get("groupChat"),
        "subagents": entry.get("subagents") if isinstance(entry.get("subagents"), dict) else None,
        "runRetries": run_retries,
        "embeddedAgent": entry.get("embeddedAgent") if isinstance(entry.get("embeddedAgent"), dict) else None,
        "sandbox": entry.get("sandbox"),
        "tools": entry.get("tools"),
    }
    # models: include if present.
    if "models" in entry and entry["models"]:
        result["models"] = entry["models"]
    # modelPolicy: include only when it has an explicit allow list.
    if _has_explicit_model_policy_allow(entry.get("modelPolicy")):
        result["modelPolicy"] = entry["modelPolicy"]

    return result


# ---------------------------------------------------------------------------
# Directory resolution
# ---------------------------------------------------------------------------


def resolve_agent_workspace_dir(
    cfg: dict[str, Any],
    agent_id: str,
    env: dict[str, str] | None = None,
) -> str:
    """Resolve the workspace directory for *agent_id*.

    Mirrors ``resolveAgentWorkspaceDir`` cascade:
    1. Per-agent ``workspace`` key.
    2. Default agent: ``agents.defaults.workspace`` OR ``<stateDir>/workspace``.
    3. Other agents: ``agents.defaults.workspace/<id>`` OR
       ``<stateDir>/workspace-<id>``.
    """
    effective_env = env if env is not None else dict(os.environ)
    nid = _normalize_agent_id(agent_id)
    agent_cfg = resolve_agent_config(cfg, nid)
    configured = (agent_cfg or {}).get("workspace")
    if configured:
        return _strip_null_bytes(_resolve_user_path(configured.strip(), effective_env))

    default_id = resolve_default_agent_id(cfg)
    agents_block = cfg.get("agents") if isinstance(cfg, dict) else None
    defaults_block = agents_block.get("defaults") if isinstance(agents_block, dict) else None
    fallback = None
    if isinstance(defaults_block, dict):
        raw = defaults_block.get("workspace")
        if isinstance(raw, str) and raw.strip():
            fallback = raw.strip()

    if nid == default_id:
        if fallback:
            return _strip_null_bytes(_resolve_user_path(fallback, effective_env))
        return _strip_null_bytes(_resolve_default_agent_workspace_dir(effective_env))

    if fallback:
        return _strip_null_bytes(
            os.path.join(_resolve_user_path(fallback, effective_env), nid)
        )
    state_dir = _resolve_state_dir(effective_env)
    return _strip_null_bytes(os.path.join(state_dir, f"workspace-{nid}"))


def resolve_agent_dir(
    cfg: dict[str, Any],
    agent_id: str,
    env: dict[str, str] | None = None,
) -> str:
    """Resolve the agent state directory (``agentDir``) for *agent_id*.

    Mirrors ``resolveAgentDir``. Registers the resolved path in the
    process-local dir registry as a side-effect (matches TS behavior).

    Default: ``<stateDir>/agents/<id>/agent``
    """
    effective_env = env if env is not None else dict(os.environ)
    nid = _normalize_agent_id(agent_id)
    agent_cfg = resolve_agent_config(cfg, nid)
    configured = (agent_cfg or {}).get("agentDir")
    if configured and isinstance(configured, str) and configured.strip():
        agent_dir = _resolve_user_path(configured.strip(), effective_env)
        register_resolved_agent_dir(nid, agent_dir, env=effective_env)
        return agent_dir

    state_dir = _resolve_state_dir(effective_env)
    agent_dir = os.path.join(state_dir, "agents", nid, "agent")
    register_resolved_agent_dir(nid, agent_dir, env=effective_env)
    return agent_dir


def resolve_default_agent_dir(
    cfg: dict[str, Any],
    env: dict[str, str] | None = None,
) -> str:
    """Resolve the agentDir for the default agent.

    Mirrors ``resolveDefaultAgentDir``.
    """
    return resolve_agent_dir(cfg, resolve_default_agent_id(cfg), env)


def resolve_agent_context_limits(
    cfg: dict[str, Any] | None,
    agent_id: str | None = None,
) -> dict[str, Any] | None:
    """Resolve effective context limits for *agent_id*.

    Mirrors ``resolveAgentContextLimits``: merges per-agent + defaults.
    """
    defaults: dict[str, Any] | None = None
    if isinstance(cfg, dict):
        agents_block = cfg.get("agents")
        if isinstance(agents_block, dict):
            d = agents_block.get("defaults")
            if isinstance(d, dict):
                cl = d.get("contextLimits")
                if isinstance(cl, dict):
                    defaults = cl

    if not cfg or not agent_id:
        return defaults

    agent_cfg = resolve_agent_config(cfg, agent_id)
    if agent_cfg is None:
        return defaults
    return agent_cfg.get("contextLimits") or defaults


__all__ = [
    "DEFAULT_AGENT_ID",
    "list_agent_entries",
    "list_agent_ids",
    "resolve_agent_config",
    "resolve_agent_context_limits",
    "resolve_agent_dir",
    "resolve_agent_workspace_dir",
    "resolve_default_agent_dir",
    "resolve_default_agent_id",
]
