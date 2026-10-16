"""TokenJuice infra plugin definition.

OpenClaw parity: mirrors the OpenClaw ``tokenjuice`` infra
extension (10 files in the OpenClaw source).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from jarvis_sdk import Plugin


_LOG = logging.getLogger("tokenjuice")


def compact_tool_result(event: Any, ctx: Any) -> Any:
    """Agent tool result middleware that compacts noisy exec/bash results."""
    # Check if plugin is enabled
    config = getattr(ctx, "config", {})
    plugins_config = config.get("plugins", {}).get("entries", {})
    tj_config = plugins_config.get("tokenjuice", {})
    if not tj_config.get("enabled", False):
        return event

    tool_name = event.get("toolName")
    if tool_name not in ("exec", "bash"):
        return event

    input_cmd = event.get("input", {}).get("command", "")
    if not input_cmd:
        return event

    # Safe-inventory policy:
    # 1. Exact file reads stay raw
    if input_cmd.startswith(("cat ", "head ", "tail ")):
        return event

    # 2. Unsafe mixed command sequences stay raw
    # Note: we only check basic shell operators to be safe
    if any(c in input_cmd for c in ("&&", "||", ";", "|", ">", ">>")):
        return event

    # 3. Standalone repository-inventory commands compact
    content = event.get("content", [])
    if not content:
        return event

    new_content = []
    for c in content:
        if c.get("type") == "text":
            text = c.get("text", "")
            lines = text.splitlines()
            if len(lines) > 50:
                compacted = "\\n".join(
                    lines[:25]
                    + [f"... (tokenjuice: compacted {len(lines) - 50} lines) ..."]
                    + lines[-25:]
                )
                new_content.append({"type": "text", "text": compacted})
            else:
                new_content.append(c)
        else:
            new_content.append(c)

    new_event = dict(event)
    new_event["content"] = new_content
    return new_event


@dataclass(frozen=True, slots=True)
class TokenJuicePlugin(Plugin):
    """TokenJuice infra descriptor."""

    id: str = "tokenjuice"
    kind: str = "infra"
    version: str = "0.1.0"
    description: str = "Token usage accounting + reporting."
    metadata: dict[str, Any] = field(default_factory=dict)

    def init(self, ctx: Any) -> None:
        """Infra init hook."""
        if hasattr(ctx, "registerAgentToolResultMiddleware"):
            ctx.registerAgentToolResultMiddleware(compact_tool_result)


tokenjuice_plugin = TokenJuicePlugin()
entry = tokenjuice_plugin
