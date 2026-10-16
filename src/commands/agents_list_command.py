"""jarvis.commands.agents_list_command — ``jarvis agents list [--bindings]``.

OpenClaw parity: mirrors ``src/commands/agents.commands.list.ts``.

Produces either:
- Human-readable text summary (default)
- JSON array of agent summaries (``--json``)

When ``--bindings`` is set, each agent summary includes the routing rules
bound to it, matching the output of ``openclaw agents list --bindings``.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

from src.agents.agent_scope_config import (
    list_agent_ids,
    resolve_default_agent_id,
    resolve_agent_config,
    resolve_agent_workspace_dir,
)
from src.routing.config_bindings import list_route_bindings
from src.routing.agent_id import normalize_agent_id
from .binding_format import describe_binding


# ---------------------------------------------------------------------------
# Agent summary shape
# ---------------------------------------------------------------------------


def _shorten_home_path(path: str) -> str:
    """Replace home dir prefix with ~ for brevity. Mirrors ``shortenHomePath``."""
    home = os.path.expanduser("~")
    if path.startswith(home + os.sep):
        return "~" + path[len(home):]
    return path


def build_agent_summaries(
    cfg: dict[str, Any],
    env: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Build base agent summary list from config.

    Mirrors ``buildAgentSummaries``.
    """
    default_agent_id = normalize_agent_id(resolve_default_agent_id(cfg))
    summaries: list[dict[str, Any]] = []

    for agent_id in list_agent_ids(cfg):
        agent_cfg = resolve_agent_config(cfg, agent_id)
        try:
            workspace = resolve_agent_workspace_dir(cfg, agent_id, env)
            workspace_display = _shorten_home_path(workspace)
        except Exception:
            workspace_display = None

        summary: dict[str, Any] = {
            "id": agent_id,
            "isDefault": agent_id == default_agent_id,
            "configured": agent_cfg is not None,
        }
        if agent_cfg:
            name = (agent_cfg.get("name") or "").strip()
            if name:
                summary["name"] = name
            model = agent_cfg.get("model")
            if model:
                summary["model"] = model
        if workspace_display:
            summary["workspace"] = workspace_display

        summaries.append(summary)

    return summaries


def _format_summary(summary: dict[str, Any]) -> str:
    """Format one agent summary as human text. Mirrors ``formatSummary``."""
    lines: list[str] = []

    label = summary["id"]
    if summary.get("name"):
        label = f"{summary['name']} ({summary['id']})"
    default_marker = " [default]" if summary.get("isDefault") else ""
    lines.append(f"  {label}{default_marker}")

    if summary.get("workspace"):
        lines.append(f"    Workspace: {summary['workspace']}")
    if summary.get("model"):
        lines.append(f"    Model:     {summary['model']}")
    if summary.get("routes"):
        lines.append("    Routes:")
        for route in summary["routes"]:
            lines.append(f"      - {route}")
    if summary.get("bindingDetails"):
        lines.append("    Routing rules:")
        for rule in summary["bindingDetails"]:
            lines.append(f"      - {rule}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main command function
# ---------------------------------------------------------------------------


def agents_list_command(
    *,
    bindings: bool = False,
    json_output: bool = False,
    cfg: dict[str, Any],
    env: dict[str, str] | None = None,
    out=None,
) -> None:
    """Print or JSON-dump configured agent summaries.

    Mirrors ``agentsListCommand`` from ``agents.commands.list.ts``.

    Parameters
    ----------
    bindings:
        When True, enrich summaries with per-agent routing binding details.
    json_output:
        When True, write JSON to *out* instead of human text.
    cfg:
        Jarvis config dict.
    env:
        Optional env override for path resolution.
    out:
        Output stream (defaults to sys.stdout).
    """
    if out is None:
        out = sys.stdout

    summaries = build_agent_summaries(cfg, env)

    # Build per-agent binding map.
    binding_map: dict[str, list[dict[str, Any]]] = {}
    for binding in list_route_bindings(cfg):
        agent_id = normalize_agent_id(binding.get("agentId", ""))
        binding_map.setdefault(agent_id, []).append(binding)

    # Enrich summaries with binding details when requested.
    if bindings:
        for summary in summaries:
            agent_bindings = binding_map.get(summary["id"], [])
            if agent_bindings:
                summary["bindingDetails"] = [describe_binding(b) for b in agent_bindings]
            elif summary.get("isDefault"):
                summary["routes"] = ["default (no explicit rules)"]

    if json_output:
        out.write(json.dumps(summaries, indent=2, ensure_ascii=False))
        out.write("\n")
        return

    lines = ["Agents:"]
    for summary in summaries:
        lines.append(_format_summary(summary))

    if bindings:
        lines.append(
            "\nRouting rules map channel/account/peer to an agent. "
            "Use --bindings to see rules."
        )

    print("\n".join(lines), file=out)


__all__ = [
    "agents_list_command",
    "build_agent_summaries",
]
