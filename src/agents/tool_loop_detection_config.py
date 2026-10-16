"""jarvis.agents.tool_loop_detection_config — resolve loop detection config.

OpenClaw parity: mirrors
``openclaw-main/src/agents/tool-loop-detection-config.ts``.
"""
from __future__ import annotations

from typing import Any, Optional


def resolve_agent_config(cfg: dict[str, Any], agent_id: str) -> Optional[dict[str, Any]]:
    """Helper to extract agent-specific config from a global config.
    In JARVIS, this would usually be under `agents[agent_id]`.
    """
    agents = cfg.get("agents", {})
    if isinstance(agents, dict):
        return agents.get(agent_id)
    return None


def resolve_tool_loop_detection_config(
    cfg: Optional[dict[str, Any]] = None,
    agent_id: Optional[str] = None
) -> Optional[dict[str, Any]]:
    """Resolves effective tool loop-detection config by overlaying agent settings
    on globals.
    
    Mirrors: `resolveToolLoopDetectionConfig`
    """
    if cfg is None:
        return None

    tools_cfg = cfg.get("tools", {})
    global_loop = tools_cfg.get("loopDetection") if isinstance(tools_cfg, dict) else None
    
    agent_loop = None
    if agent_id:
        agent_cfg = resolve_agent_config(cfg, agent_id)
        if agent_cfg and isinstance(agent_cfg, dict):
            agent_tools_cfg = agent_cfg.get("tools", {})
            if isinstance(agent_tools_cfg, dict):
                agent_loop = agent_tools_cfg.get("loopDetection")

    if not agent_loop:
        return global_loop
    if not global_loop:
        return agent_loop

    # Overlay agent on global
    merged = dict(global_loop)
    merged.update(agent_loop)

    # Detectors overlay
    global_detectors = global_loop.get("detectors", {})
    agent_detectors = agent_loop.get("detectors", {})
    if isinstance(global_detectors, dict) and isinstance(agent_detectors, dict):
        merged_detectors = dict(global_detectors)
        merged_detectors.update(agent_detectors)
        merged["detectors"] = merged_detectors
    elif agent_detectors:
        merged["detectors"] = agent_detectors

    # PostCompactionGuard overlay
    global_guard = global_loop.get("postCompactionGuard", {})
    agent_guard = agent_loop.get("postCompactionGuard", {})
    if isinstance(global_guard, dict) and isinstance(agent_guard, dict):
        merged_guard = dict(global_guard)
        merged_guard.update(agent_guard)
        merged["postCompactionGuard"] = merged_guard
    elif agent_guard:
        merged["postCompactionGuard"] = agent_guard

    return merged


__all__ = ["resolve_tool_loop_detection_config"]
