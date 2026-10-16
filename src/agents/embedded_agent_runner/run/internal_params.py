"""jarvis.agents.embedded_agent_runner.run.internal_params — orchestrator-internal params.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/internal-params.ts``.

Public surface (mirrors the OpenClaw source):

- :data:`RunEmbeddedAgentInternalParams` — the internal
  parameter shape (extends :data:`RunEmbeddedAgentParams`
  with orchestrator-injected fields).
- :data:`RunEmbeddedAgentParamsWithSessionFile` — the
  internal parameter shape with a resolved ``sessionFile``.

Phase 7.6a — focused minimal port.

The OpenClaw source's ``AgentExecutionAuthBinding`` +
``SystemAgentToolOptions`` types land in 7.2+ (when the
specialized sub-modules are ported).
"""
from __future__ import annotations

from typing import Any



#: The orchestrator-internal parameter shape. Mirrors
#: :class:`RunEmbeddedAgentInternalParams``
#: (``internal-params.ts:5-10``).
class RunEmbeddedAgentInternalParams(dict[str, Any]):
    """Constructible dict-like container for internal run params."""


#: The internal parameter shape with a resolved session file.
#: Mirrors :class:`RunEmbeddedAgentParamsWithSessionFile``
#: (``internal-params.ts:12-14``).
class RunEmbeddedAgentParamsWithSessionFile(dict[str, Any]):
    """Constructible dict-like container for run params with a session file."""


# Field names that the orchestrator injects into
# :data:`RunEmbeddedAgentInternalParams`.
_RUN_INTERNAL_FIELDS: tuple = (
    "onSuccessfulAuthBinding",
    "authProfileStateMode",
    "systemAgentTool",
)


# Field names that the orchestrator injects into
# :data:`RunEmbeddedAgentParamsWithSessionFile` (in addition
# to the internal fields).
_RUN_WITH_SESSION_FILE_FIELDS: tuple = ("sessionFile",)


def get_internal_param_field_names() -> tuple:
    """Return the orchestrator-injected field names."""
    return _RUN_INTERNAL_FIELDS + _RUN_WITH_SESSION_FILE_FIELDS


__all__ = [
    "RunEmbeddedAgentInternalParams",
    "RunEmbeddedAgentParamsWithSessionFile",
    "get_internal_param_field_names",
]
