"""jarvis.agents.embedded_agent_runner.logger — subsystem logger.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/logger.ts``.

Public surface (mirrors the OpenClaw
source):

- :data:`log` — the shared subsystem
  logger for embedded-agent runner
  internals.

Phase 7.0 — focused minimal port.
The Python port uses :mod:`logging`
(the OpenClaw source uses a
``createSubsystemLogger`` helper
from :mod:`@openclaw/logging/subsystem.js`
that emits structured records to a
custom sink; the Python port's
:mod:`logging` is the standard
equivalent).
"""
from __future__ import annotations

import logging


#: The shared subsystem logger for
#: embedded-agent runner internals.
#: Mirrors :data:`log`
#: (``logger.ts:9``).
log = logging.getLogger("jarvis.agents.embedded_agent_runner")


__all__ = ["log"]
