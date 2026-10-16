"""jarvis.commands.agents_bind_command — ``jarvis agents bind/bindings/unbind``.

OpenClaw parity: mirrors ``src/commands/agents.commands.bind.ts``.

Provides pure command functions for:
  - ``agents_bindings_list_command`` — list bindings for one or all agents
  - ``agents_bind_command`` — add new bindings to an agent
  - ``agents_unbind_command`` — remove bindings from an agent

These functions accept a ``cfg`` dict and return a result dict (no I/O).
The caller (CLI entry point) handles config file writes and terminal output.
"""

from __future__ import annotations

from typing import Any

from src.routing.agent_id import normalize_agent_id
from src.agents.agent_scope_config import (
    list_agent_entries,
    resolve_default_agent_id,
)
from src.routing.config_bindings import list_route_bindings
from .binding_format import describe_binding
from .agents_bindings import (
    apply_agent_bindings,
    parse_binding_specs,
    remove_agent_bindings,
)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _has_agent(cfg: dict[str, Any], agent_id: str) -> bool:
    """True when *agent_id* is a configured agent or the effective default."""
    target = normalize_agent_id(agent_id)
    entries = list_agent_entries(cfg)
    if not entries:
        return target == normalize_agent_id(resolve_default_agent_id(cfg))
    return any(normalize_agent_id(e.get("id", "")) == target for e in entries)


def _resolve_agent_id(
    cfg: dict[str, Any],
    agent_input: str | None,
    *,
    fallback_to_default: bool = False,
) -> str | None:
    """Normalize agent id from user input. Mirrors ``resolveAgentId``."""
    stripped = (agent_input or "").strip()
    if stripped:
        return normalize_agent_id(stripped)
    if fallback_to_default:
        return normalize_agent_id(resolve_default_agent_id(cfg))
    return None


# ---------------------------------------------------------------------------
# agents bindings (list)
# ---------------------------------------------------------------------------


def agents_bindings_list_command(
    cfg: dict[str, Any],
    *,
    agent: str | None = None,
) -> dict[str, Any]:
    """List route bindings, optionally filtered to one agent.

    Mirrors the ``bindings list`` subcommand.

    Returns ``{"bindings": [...], "lines": [...]}``.
    ``lines`` is the human-readable output; ``bindings`` is the raw list.
    """
    all_bindings = list(list_route_bindings(cfg))

    if agent:
        target_id = normalize_agent_id(agent)
        all_bindings = [
            b for b in all_bindings
            if normalize_agent_id(b.get("agentId", "")) == target_id
        ]

    lines: list[str] = []
    if not all_bindings:
        if agent:
            lines.append(f"No routing bindings configured for agent {agent!r}.")
        else:
            lines.append("No routing bindings configured.")
    else:
        for binding in all_bindings:
            agent_id = normalize_agent_id(binding.get("agentId", ""))
            desc = describe_binding(binding)
            lines.append(f"  {agent_id} <- {desc}")

    return {"bindings": all_bindings, "lines": lines}


# ---------------------------------------------------------------------------
# agents bind (add)
# ---------------------------------------------------------------------------


def agents_bind_command(
    cfg: dict[str, Any],
    *,
    agent: str | None = None,
    bind_specs: list[str] | None = None,
) -> dict[str, Any]:
    """Add route bindings to an agent.

    Mirrors the ``agents bind`` subcommand.

    Returns a result dict:
        {
            "ok": bool,
            "error": str | None,
            "config": dict | None,    # updated cfg on success
            "added": [...],
            "updated": [...],
            "skipped": [...],
            "conflicts": [...],
            "lines": [...],           # human output lines
        }
    """
    agent_id = _resolve_agent_id(cfg, agent, fallback_to_default=True)
    if not agent_id:
        return {
            "ok": False,
            "error": "Unable to resolve agent id. Run `jarvis agents list` to choose one.",
            "config": None,
        }
    if not _has_agent(cfg, agent_id):
        return {
            "ok": False,
            "error": f"Agent {agent_id!r} not found. Run `jarvis agents list` to see configured agents.",
            "config": None,
        }

    specs = [s.strip() for s in (bind_specs or []) if s.strip()]
    if not specs:
        return {
            "ok": False,
            "error": "No binding specs provided. Use --bind channel[/accountId[/kind:id]].",
            "config": None,
        }

    parsed = parse_binding_specs(agent_id=agent_id, specs=specs, config=cfg)
    if parsed["errors"]:
        return {
            "ok": False,
            "error": "\n".join(parsed["errors"]),
            "config": None,
        }

    result = apply_agent_bindings(cfg, parsed["bindings"])
    lines: list[str] = []

    for b in result["added"]:
        lines.append(f"  Added:   {agent_id} <- {describe_binding(b)}")
    for b in result["updated"]:
        lines.append(f"  Updated: {agent_id} <- {describe_binding(b)}")
    for b in result["skipped"]:
        lines.append(f"  Skipped (already exists): {describe_binding(b)}")
    for c in result["conflicts"]:
        lines.append(
            f"  Conflict: {describe_binding(c['binding'])} is already bound to {c['existingAgentId']!r}"
        )

    has_conflicts = bool(result["conflicts"])
    return {
        "ok": not has_conflicts,
        "error": None,
        "config": result["config"],
        "added": result["added"],
        "updated": result["updated"],
        "skipped": result["skipped"],
        "conflicts": result["conflicts"],
        "lines": lines,
    }


# ---------------------------------------------------------------------------
# agents unbind (remove)
# ---------------------------------------------------------------------------


def agents_unbind_command(
    cfg: dict[str, Any],
    *,
    agent: str | None = None,
    bind_specs: list[str] | None = None,
    all_bindings: bool = False,
) -> dict[str, Any]:
    """Remove route bindings from an agent.

    Mirrors the ``agents unbind`` subcommand.

    Returns ``{"ok": bool, "error": str | None, "config": dict | None, "removed": [...], "lines": [...]}``.
    """
    agent_id = _resolve_agent_id(cfg, agent, fallback_to_default=True)
    if not agent_id:
        return {
            "ok": False,
            "error": "Unable to resolve agent id.",
            "config": None,
            "removed": [],
            "lines": [],
        }
    if not _has_agent(cfg, agent_id):
        return {
            "ok": False,
            "error": f"Agent {agent_id!r} not found.",
            "config": None,
            "removed": [],
            "lines": [],
        }

    # Collect bindings to remove.
    if all_bindings:
        to_remove = [
            b for b in list_route_bindings(cfg)
            if normalize_agent_id(b.get("agentId", "")) == agent_id
        ]
    else:
        specs = [s.strip() for s in (bind_specs or []) if s.strip()]
        if not specs:
            return {
                "ok": False,
                "error": "Provide --bind specs or --all to remove all bindings.",
                "config": None,
                "removed": [],
                "lines": [],
            }
        parsed = parse_binding_specs(agent_id=agent_id, specs=specs, config=cfg)
        if parsed["errors"]:
            return {
                "ok": False,
                "error": "\n".join(parsed["errors"]),
                "config": None,
                "removed": [],
                "lines": [],
            }
        to_remove = parsed["bindings"]

    if not to_remove:
        return {
            "ok": True,
            "error": None,
            "config": cfg,
            "removed": [],
            "lines": [f"No matching bindings found for agent {agent_id!r}."],
        }

    result = remove_agent_bindings(cfg, to_remove)
    lines = [f"  Removed: {describe_binding(b)}" for b in result["removed"]]
    for b in result.get("notFound", []):
        lines.append(f"  Not found: {describe_binding(b)}")

    return {
        "ok": True,
        "error": None,
        "config": result["config"],
        "removed": result["removed"],
        "lines": lines,
    }


__all__ = [
    "agents_bindings_list_command",
    "agents_bind_command",
    "agents_unbind_command",
]
