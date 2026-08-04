"""jarvis.config.zod_schema_agent_defaults — agent default config Zod schema.

OpenClaw parity: mirrors
``openclaw-main/src/config/zod-schema.agent-defaults.ts``.

Focused minimal port: thin facade with placeholder Zod schemas. The
public surface is exposed as Python type stubs; the real Zod validator
lands with the schema validator port.
"""
from __future__ import annotations

from typing import Any, Literal


#: Silent-reply policy values.
SilentReplyPolicy = Literal["allow", "disallow"]


#: Agent thinking levels.
AgentThinkingLevel = Literal[
    "off", "minimal", "low", "medium", "high", "xhigh", "adaptive", "max", "ultra",
]


#: Optional bootstrap file names.
OptionalBootstrapFileName = Literal[
    "SOUL.md", "USER.md", "HEARTBEAT.md", "IDENTITY.md",
]


#: Agent defaults config schema (zod facade).
AgentDefaultsSchema: Any = None  # z.object({...}).strict().optional()


#: Silent-reply policy config schema (zod facade).
SilentReplyPolicyConfigSchema: Any = None


__all__ = [
    "SilentReplyPolicy",
    "AgentThinkingLevel",
    "OptionalBootstrapFileName",
    "AgentDefaultsSchema",
    "SilentReplyPolicyConfigSchema",
]
