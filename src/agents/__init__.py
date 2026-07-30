"""jarvis.agents — OpenClaw ``src/agents/`` parity stub.

The Python port mirrors the OpenClaw ``src/agents/``
subdir; the module bodies land incrementally per the
V2 plan as the corresponding subsystem is ported.

Phase 6.0 — scaffolding + helpers + small types.

The OpenClaw source has no ``src/agents/index.ts``
(consumers import from ``src/agents/sessions/``,
``src/agents/runtime/``, etc. directly). The Python
port keeps the same convention: this ``__init__.py``
only re-exports the sub-package public surface so
callers can use ``from jarvis.agents.sessions import
...`` exactly the way they would in OpenClaw, and
``from jarvis.agents import create_agent_session,
AgentSession, ...`` once the corresponding modules
land in later phases.
"""
from __future__ import annotations

# Re-export the Phase-6.0 sessions surface so callers
# can use ``from jarvis.agents import ...`` for the
# leaf modules as well. The full public surface
# (create_agent_session, AgentSession, etc.) lands
# in later phases; this stub stays import-safe.
from . import sessions  # noqa: F401  (re-export sub-package)


__all__ = [
    "sessions",
]
