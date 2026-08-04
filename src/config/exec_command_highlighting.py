"""jarvis.config.exec_command_highlighting — exec highlighting config resolver.

OpenClaw parity: mirrors
``openclaw-main/src/config/exec-command-highlighting.ts``.
"""
from __future__ import annotations

from typing import Any, Optional


def _normalize_agent_id(value) -> Optional[str]:
    if not isinstance(value, str):
        return None
    trimmed = value.strip().lower()
    return trimmed or None


def resolve_exec_command_highlighting(params: dict) -> bool:
    """Resolve whether exec command highlighting is enabled for the current agent scope.

    Mirrors :func:`resolveExecCommandHighlighting`
    (``shared/config/exec-command-highlighting.ts``).
    """
    config = params.get("config") or {}
    global_value = ((config.get("tools") or {}).get("exec") or {}).get("commandHighlighting")
    agent_id = _normalize_agent_id(params.get("agentId"))
    agent_value = None
    if agent_id:
        for entry in ((config.get("agents") or {}).get("list") or []):
            if not isinstance(entry, dict):
                continue
            if _normalize_agent_id(entry.get("id")) == agent_id:
                agent_value = (
                    ((entry.get("tools") or {}).get("exec") or {}).get("commandHighlighting")
                )
                break
    # Agent-scoped config overrides the global exec setting;
    # absent config stays disabled.
    return agent_value if agent_value is not None else (global_value if global_value is not None else False)


__all__ = ["resolve_exec_command_highlighting"]
