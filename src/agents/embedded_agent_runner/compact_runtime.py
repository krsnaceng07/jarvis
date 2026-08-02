"""jarvis.agents.embedded_agent_runner.compact_runtime — lazy runtime loader.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/compact.runtime.ts``.

Public surface (mirrors the OpenClaw
source):

- :func:`compact_embedded_agent_session_direct` —
  load the compaction runtime on
  demand + forward the direct
  compaction call.

Phase 7.2a — focused minimal port.
The full runtime integration lands
in 7.2c (when the main
:mod:`compact` module is ported)."""
from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Optional

from .compact_runtime_types import (
    CompactEmbeddedAgentSessionDirect,
)


_LOG = logging.getLogger(
    "jarvis.agents.embedded_agent_runner.compact_runtime"
)


#: The lazily-loaded runtime module.
#: Phase 7.2a — STUB. The real
#: :func:`compact_embedded_agent_session_direct`
#: function lands in 7.2c.
_runtime_module: Optional[Any] = None


def _load_compact_runtime() -> Any:
    """Load the compaction runtime
    module (lazy). Mirrors the
    OpenClaw source's
    :func:`loadCompactRuntime`
    (``compact.runtime.ts:9-11`).

    Phase 7.2a — STUB. Returns
    ``None`` until 7.2c ports the
    main :mod:`compact` module.
    """
    global _runtime_module
    if _runtime_module is None:
        # Phase 7.2a — STUB.
        _LOG.debug(
            "compact runtime not yet loaded; "
            "lands in 7.2c"
        )
        _runtime_module = None
    return _runtime_module


async def compact_embedded_agent_session_direct(
    *args: Any,
    **kwargs: Any,
) -> dict:
    """Load the compaction runtime on
    demand + forward the direct
    compaction call. Mirrors
    :func:`compactEmbeddedAgentSessionDirect`
    (``compact.runtime.ts:14-19`).

    Phase 7.2a — STUB. The real
    implementation lands in 7.2c.
    """
    runtime = _load_compact_runtime()
    if runtime is None:
        raise NotImplementedError(
            "compact_embedded_agent_session_direct is a stub in 7.2a; "
            "the real runtime lands in 7.2c"
        )
    return await runtime.compact_embedded_agent_session_direct(
        *args, **kwargs
    )


__all__ = ["compact_embedded_agent_session_direct"]
