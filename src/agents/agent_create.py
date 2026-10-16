"""jarvis.agents.agent_create — agent creation entry point.

OpenClaw parity: mirrors ``src/agents/agent-create.ts``.

``create_agent`` orchestrates workspace creation, config mutation, and
optional binding registration for a new isolated agent.

Result shapes
-------------
``CreateAgentResult`` is a discriminated union:
- ``{"status": "created", "agent_id": ..., "name": ..., "workspace": ..., ...}``
- ``{"status": "error", "reason": ..., "message": ..., ...}``

Error reasons mirror ``CreateError["reason"]`` from TS:
``"invalid-name"`` | ``"reserved-id"`` | ``"already-exists"`` |
``"invalid-bindings"`` | ``"unsafe-identity-file"``
"""

from __future__ import annotations

import re
from typing import Any, Literal, TypedDict

from src.routing.agent_id import normalize_agent_id
from .agent_scope_config import (
    DEFAULT_AGENT_ID,
    list_agent_ids,
    resolve_agent_dir,
    resolve_agent_workspace_dir,
)
from .workspace import (
    ensure_agent_workspace,
    write_bootstrap_files,
)

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

_CreateErrorReason = Literal[
    "invalid-name",
    "reserved-id",
    "already-exists",
    "invalid-bindings",
    "unsafe-identity-file",
]


class CreateAgentSuccess(TypedDict, total=False):
    status: Literal["created"]
    agent_id: str
    name: str
    workspace: str
    agent_dir: str
    model: str | None
    bootstrap_pending: bool


class CreateAgentError(TypedDict):
    status: Literal["error"]
    reason: str
    message: str
    agent_id: str | None


CreateAgentResult = CreateAgentSuccess | CreateAgentError


# ---------------------------------------------------------------------------
# Reserved / system agent ids
# ---------------------------------------------------------------------------

#: Mirrors ``isReservedSystemAgentId`` from ``src/system-agent/agent-id.ts``.
_RESERVED_AGENT_IDS: frozenset[str] = frozenset(
    {
        "system",
        "jarvis",
        "openclaw",
        "default",
        "admin",
        "root",
        "internal",
    }
)

#: Valid agent name characters (human name, not id).
_VALID_NAME_RE = re.compile(r"^[\w][\w\s\-.']*$", re.UNICODE)

#: Max name length (matches TS).
_MAX_NAME_LEN = 64


def _is_reserved_system_agent_id(agent_id: str) -> bool:
    return agent_id.lower() in _RESERVED_AGENT_IDS


def _name_to_agent_id(name: str) -> str:
    """Derive a valid agent id from a human name.

    Mirrors the slug derivation in OpenClaw's ``createAgent``:
    lowercase, replace non-word chars with hyphens, collapse and strip.
    """
    slug = re.sub(r"[^\w]+", "-", name.lower()).strip("-")
    return slug or "agent"


# ---------------------------------------------------------------------------
# Config mutation helpers
# ---------------------------------------------------------------------------


def _apply_agent_config(
    cfg: dict[str, Any],
    *,
    agent_id: str,
    name: str,
    workspace: str | None = None,
    agent_dir: str | None = None,
    model: str | None = None,
    is_default: bool = False,
) -> None:
    """Insert or update an agent entry in *cfg*.

    Mutates *cfg* in place. Mirrors ``applyAgentConfig``.
    """
    if not isinstance(cfg.get("agents"), dict):
        cfg["agents"] = {}
    agents_block: dict[str, Any] = cfg["agents"]
    if not isinstance(agents_block.get("list"), list):
        agents_block["list"] = []
    entries: list[dict[str, Any]] = agents_block["list"]

    # Find existing entry to update.
    nid = normalize_agent_id(agent_id)
    for entry in entries:
        if isinstance(entry, dict) and normalize_agent_id(entry.get("id", "")) == nid:
            entry["name"] = name
            if workspace is not None:
                entry["workspace"] = workspace
            if agent_dir is not None:
                entry["agentDir"] = agent_dir
            if model is not None:
                entry["model"] = model
            if is_default:
                entry["default"] = True
            return

    # New entry.
    new_entry: dict[str, Any] = {"id": agent_id, "name": name}
    if workspace is not None:
        new_entry["workspace"] = workspace
    if agent_dir is not None:
        new_entry["agentDir"] = agent_dir
    if model is not None:
        new_entry["model"] = model
    if is_default:
        new_entry["default"] = True
    entries.append(new_entry)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def create_agent(
    *,
    name: str,
    cfg: dict[str, Any],
    workspace: str | None = None,
    model: str | None = None,
    agent_dir: str | None = None,
    env: dict[str, str] | None = None,
    is_default: bool = False,
    write_bootstrap: bool = True,
    binding_specs: list[str] | None = None,
) -> CreateAgentResult:
    """Create a new isolated agent.

    Mirrors ``createAgent`` from ``agent-create.ts``.

    Parameters
    ----------
    name:
        Human-readable name for the new agent.
    cfg:
        Jarvis config dict (mutated in place to add the new entry).
    workspace:
        Explicit workspace dir override. When ``None`` the default cascade
        is used after the entry is added to config.
    model:
        Default model string for this agent.
    agent_dir:
        Explicit agentDir override.
    env:
        Environment dict for path resolution.
    is_default:
        When True, mark this agent as the default in config.
    write_bootstrap:
        When True (default), write starter ``AGENTS.md`` / ``SOUL.md``.
    binding_specs:
        Optional list of binding spec strings (``--bind`` flag values).
        Validated but not applied in this pure function; the caller must
        apply them to the config.

    Returns
    -------
    CreateAgentResult
        Success or error dict.
    """
    raw_name = name.strip()

    # Validate name.
    if not raw_name or len(raw_name) > _MAX_NAME_LEN:
        return {
            "status": "error",
            "reason": "invalid-name",
            "message": f"Agent name must be 1–{_MAX_NAME_LEN} characters.",
            "agent_id": None,
        }
    if not _VALID_NAME_RE.match(raw_name):
        return {
            "status": "error",
            "reason": "invalid-name",
            "message": (
                "Agent name may only contain letters, digits, spaces, hyphens, "
                "apostrophes, and periods, and must start with a letter or digit."
            ),
            "agent_id": None,
        }

    agent_id = _name_to_agent_id(raw_name)

    # Check reserved ids.
    if _is_reserved_system_agent_id(agent_id):
        return {
            "status": "error",
            "reason": "reserved-id",
            "message": f"Agent id {agent_id!r} is reserved.",
            "agent_id": agent_id,
        }

    # Check for duplicates.
    existing_ids = list_agent_ids(cfg)
    if agent_id in existing_ids and agent_id != DEFAULT_AGENT_ID:
        return {
            "status": "error",
            "reason": "already-exists",
            "message": f"An agent with id {agent_id!r} already exists.",
            "agent_id": agent_id,
        }

    # Validate binding specs if provided (parse-only check).
    if binding_specs:
        for spec in binding_specs:
            if not isinstance(spec, str) or not spec.strip():
                return {
                    "status": "error",
                    "reason": "invalid-bindings",
                    "message": f"Invalid binding spec: {spec!r}",
                    "agent_id": agent_id,
                }

    # Mutate config to add the new entry (needed for path resolution below).
    _apply_agent_config(
        cfg,
        agent_id=agent_id,
        name=raw_name,
        workspace=workspace,
        agent_dir=agent_dir,
        model=model,
        is_default=is_default,
    )

    # Resolve effective workspace and agentDir from the now-updated config.
    resolved_workspace = resolve_agent_workspace_dir(cfg, agent_id, env)
    resolved_agent_dir = resolve_agent_dir(cfg, agent_id, env)

    # Create workspace directory and write bootstrap files.
    try:
        ensure_agent_workspace(resolved_workspace)
        bootstrap_pending = False
        if write_bootstrap:
            write_bootstrap_files(resolved_workspace, name=raw_name)
    except OSError as exc:
        return {
            "status": "error",
            "reason": "unsafe-identity-file",
            "message": f"Failed to create workspace: {exc}",
            "agent_id": agent_id,
        }

    return {
        "status": "created",
        "agent_id": agent_id,
        "name": raw_name,
        "workspace": resolved_workspace,
        "agent_dir": resolved_agent_dir,
        "model": model,
        "bootstrap_pending": bootstrap_pending,
    }


__all__ = [
    "CreateAgentResult",
    "CreateAgentSuccess",
    "CreateAgentError",
    "create_agent",
]
