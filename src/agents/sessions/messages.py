"""jarvis.agents.sessions.messages — session message conversion bridge.

OpenClaw parity: mirrors
``openclaw-main/src/agents/sessions/messages.ts``.

Keeps the re-export here so legacy session code can
import the same shape from the sessions module while
the canonical message conversion logic lives in the
shared ``jarvis_agent`` agent-core package.

Parity
======
- ``convert_to_llm`` (re-exported from
  ``jarvis_agent.messages``) —
  ``messages.ts:7``.
- ``BashExecutionMessage`` (re-exported from
  ``jarvis_agent.types``) — ``messages.ts:10``.
- ``CustomMessage`` (re-exported from
  ``jarvis_agent.types``) — ``messages.ts:11``.

Phase 6.0 — scaffolding + helpers + small types.

The OpenClaw file is a thin re-export; the JARVIS
port keeps the same shape. The canonical Python
implementation lives in
``packages/agent_runtime/src/jarvis_agent/messages.py``
(Phase 5.8).
"""
from __future__ import annotations

# Re-export the agent-core message conversion
# utilities so ``from jarvis.agents.sessions.messages
# import convert_to_llm, BashExecutionMessage,
# CustomMessage`` resolves to the canonical types.
# This matches OpenClaw's
# ``export { convertToLlm } from "..../messages.js"``
# (messages.ts:7) + the type re-exports (messages.ts:9-12).
from jarvis_agent.messages import convert_to_llm
from jarvis_agent.types import BashExecutionMessage, CustomMessage


__all__ = [
    "BashExecutionMessage",
    "CustomMessage",
    "convert_to_llm",
]
