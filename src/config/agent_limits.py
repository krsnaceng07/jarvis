"""jarvis.config.agent_limits — per-agent runtime limit defaults.

OpenClaw parity: mirrors ``openclaw-main/src/config/agent-limits.ts``.
"""
from __future__ import annotations

from typing import Optional


DEFAULT_AGENT_MAX_CONCURRENT = 4
DEFAULT_SUBAGENT_MAX_CONCURRENT = 8
DEFAULT_SUBAGENT_MAX_CHILDREN_PER_AGENT = 5
DEFAULT_SUBAGENT_ARCHIVE_AFTER_MINUTES = 60
# Keep depth-1 subagents as leaves unless config explicitly opts into nesting.
DEFAULT_SUBAGENT_MAX_SPAWN_DEPTH = 1


def resolve_agent_max_concurrent(cfg: Optional[dict] = None) -> int:
    """Resolve top-level agent concurrency.

    Mirrors :func:`resolveAgentMaxConcurrent`
    (``shared/config/agent-limits.ts``).
    """
    raw = (cfg or {}).get("agents", {}).get("defaults", {}).get("maxConcurrent")
    if isinstance(raw, (int, float)) and raw == raw and raw != float("inf"):
        return max(1, int(raw))
    return DEFAULT_AGENT_MAX_CONCURRENT


def resolve_subagent_max_concurrent(cfg: Optional[dict] = None) -> int:
    """Resolve subagent concurrency.

    Mirrors :func:`resolveSubagentMaxConcurrent`
    (``shared/config/agent-limits.ts``).
    """
    raw = (cfg or {}).get("agents", {}).get("defaults", {}).get("subagents", {}).get("maxConcurrent")
    if isinstance(raw, (int, float)) and raw == raw and raw != float("inf"):
        return max(1, int(raw))
    return DEFAULT_SUBAGENT_MAX_CONCURRENT


__all__ = [
    "DEFAULT_AGENT_MAX_CONCURRENT",
    "DEFAULT_SUBAGENT_MAX_CONCURRENT",
    "DEFAULT_SUBAGENT_MAX_CHILDREN_PER_AGENT",
    "DEFAULT_SUBAGENT_ARCHIVE_AFTER_MINUTES",
    "DEFAULT_SUBAGENT_MAX_SPAWN_DEPTH",
    "resolve_agent_max_concurrent",
    "resolve_subagent_max_concurrent",
]
