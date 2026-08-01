"""jarvis.agents.sessions.agent_session — main entry.

OpenClaw parity: mirrors
``openclaw-main/src/agents/sessions/agent-session.ts``.

The :class:`AgentSession` class is the
core abstraction for agent lifecycle
+ session management. Shared by
interactive, print, and RPC modes.
Mode-specific I/O stays above this
class while the feature layers below
own session behavior.

Public surface (mirrors the OpenClaw
source):

- :class:`AgentSession` — the main
  :class:`AgentSessionTree` subclass
  that wires up agent event
  subscription, installs tool hooks,
  + builds the runtime.

Phase 6.12h — focused port.

Adaptations
-----------
- The OpenClaw source's
  :func:`this.agent.subscribe(this.handleAgentEvent)`
  delegates to the
  ``AgentSessionBase.subscribe``
  infrastructure (the session's
  :func:`handleAgentEvent` is the
  OpenClaw source's helper inside
  :class:`AgentSessionBase`). The
  Python port's
  :func:`disconnect_from_agent` /
  :func:`reconnect_to_agent` already
  handle the
  ``subscribe_events`` /
  :func:`_on_agent_event` plumbing
  (added in 6.12g). The
  :class:`AgentSession` constructor
  wires the initial subscription via
  :func:`reconnect_to_agent`.
- The OpenClaw source's
  :func:`this.installAgentToolHooks()`
  is a STUB in the Python port
  (lands in 6.13+ — the tool-hook
  plumbing is on
  :class:`AgentSessionBase`).
"""
from __future__ import annotations

import logging
from typing import Any

from .agent_session_tree import AgentSessionTree


_LOG = logging.getLogger("jarvis.agents.sessions.agent_session")


class AgentSession(AgentSessionTree):
    """The main :class:`AgentSession`
    subclass. Mirrors
    :class:`AgentSession`
    (``agent-session.ts:12-22``).

    Phase 6.12h port.
    """

    def __init__(self, config: Any) -> None:
        """Bind the session to the agent
        + persistence layers, subscribe
        to agent events, install tool
        hooks, + build the runtime.

        Mirrors the OpenClaw source's
        :class:`AgentSession`
        constructor
        (``agent-session.ts:13-21``)."""
        super().__init__(config)
        # 1. Subscribe to the agent's
        #    events. The OpenClaw source
        #    uses
        #    ``this.agent.subscribe(this.handleAgentEvent)``;
        #    the Python port's
        #    :func:`reconnect_to_agent`
        #    wires
        #    ``agent.subscribe_events`` →
        #    ``self._on_agent_event``.
        self.reconnect_to_agent()
        # 2. Install the before-/after-
        #    tool hooks on the agent.
        #    STUB in 6.12h; the full
        #    plumbing lands in 6.13+.
        try:
            self.install_agent_tool_hooks()
        except Exception:
            _LOG.debug(
                "install_agent_tool_hooks raised (stub)",
                exc_info=True,
            )
        # 3. Build the runtime.
        self.build_runtime(
            {
                "activeToolNames": self.initial_active_tool_names,
                "includeAllExtensionTools": True,
            }
        )


__all__ = [
    "AgentSession",
]
