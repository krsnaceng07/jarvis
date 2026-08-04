"""jarvis.config.zod_schema_agent_model — agent model selection schema fragments.

OpenClaw parity: mirrors
``openclaw-main/src/config/zod-schema.agent-model.ts``.
"""
from __future__ import annotations

from typing import Any


#: Agent model config schema (string or primary/fallbacks object).
AgentModelSchema: Any = None  # z.union([z.string(), z.object({...}).strict()])


#: Tool model config schema (string or primary/fallbacks/timeoutMs object).
AgentToolModelSchema: Any = None  # z.union([z.string(), z.object({...}).strict()])


def is_agent_model_value(value: Any) -> bool:
    """Validate a string-or-object agent model config value."""
    if isinstance(value, str):
        return True
    if isinstance(value, dict):
        # Object form: at most {primary?, fallbacks?}.
        return set(value.keys()) <= {"primary", "fallbacks"}
    return False


def is_agent_tool_model_value(value: Any) -> bool:
    """Validate a string-or-object tool model config value."""
    if isinstance(value, str):
        return True
    if isinstance(value, dict):
        return set(value.keys()) <= {"primary", "fallbacks", "timeoutMs"}
    return False


__all__ = [
    "AgentModelSchema",
    "AgentToolModelSchema",
    "is_agent_model_value",
    "is_agent_tool_model_value",
]
