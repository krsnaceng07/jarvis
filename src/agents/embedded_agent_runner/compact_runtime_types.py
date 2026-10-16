"""jarvis.agents.embedded_agent_runner.compact_runtime_types — runtime types.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/compact.runtime.types.ts``.

Public surface (mirrors the OpenClaw
source):

- :data:`CompactEmbeddedAgentSessionDirect` —
  the lazy-runtime signature for
  direct embedded session
  compaction.

Phase 7.2a — focused minimal port.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Awaitable, Callable


if TYPE_CHECKING:
    pass


#: The lazy-runtime signature for
#: direct embedded session
#: compaction. Mirrors
#: :class:`CompactEmbeddedAgentSessionDirect`
#: (``compact.runtime.types.ts:10-13``).
#: The Python port uses
#: :class:`Callable[[dict],
#: Awaitable[dict]]` for runtime
#: compatibility (the
#: :class:`EmbeddedAgentCompactResult`
#: type lands in 7.2c).
CompactEmbeddedAgentSessionDirect = Callable[
    [dict], Awaitable[dict]
]


__all__ = ["CompactEmbeddedAgentSessionDirect"]
