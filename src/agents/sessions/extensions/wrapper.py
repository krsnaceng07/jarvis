"""jarvis.agents.sessions.extensions.wrapper — tool wrappers.

OpenClaw parity: mirrors
``openclaw-main/src/agents/sessions/extensions/wrapper.ts``.

Phase 6.9c — ``wrapRegisteredTool`` + ``wrapRegisteredTools``
helpers. These wrap a
:class:`~jarvis.agents.sessions.extensions.types.RegisteredTool`
into a runtime-callable tool that the agent
loop can dispatch to. The OpenClaw source
delegates to ``wrapToolDefinition`` from
``../tools/tool-definition-wrapper.js``; the
Python port depends on the Phase 6.10 tool
surface (the
:mod:`jarvis.agents.sessions.tools` module).
Until Phase 6.10 lands, the wrapper is a
shim that returns a thin callable object.

Adaptations
-----------
- The OpenClaw source's
  ``wrapToolDefinition(definition, () => runner.createContext())``
  pattern is preserved — the wrapper builds
  a context provider closure over the runner.
  The Python port returns a thin
  :class:`_RegisteredToolWrapper` class that
  exposes the OpenClaw surface (name, label,
  description, parameters) + a coroutine
  ``execute(tool_call_id, params, signal, on_update, ctx)``
  that forwards to the registered tool's
  execute function.
- The OpenClaw source returns ``AgentTool``
  objects; the Python port uses
  ``dict``-shaped tool proxies (the
  ``AgentTool`` shape lands in Phase 6.10).
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from .types import ExtensionContext, RegisteredTool
from .runner import ExtensionRunner


_log = logging.getLogger("jarvis.agents.sessions.extensions.wrapper")


# ============================================================================
# Tool wrapper class
# ============================================================================


class _RegisteredToolWrapper:
    """Runtime proxy for an
    extension-registered :class:`RegisteredTool`.
    Mirrors the shape produced by
    ``wrapRegisteredTool``
    (``wrapper.ts:17-22``) — the OpenClaw
    source returns an ``AgentTool`` object
    the agent loop can call directly. The
    Python port uses a ``dict``-shaped tool
    proxy + a private coroutine ``execute``
    (the canonical :class:`AgentTool` shape
    lands in Phase 6.10)."""

    def __init__(
        self,
        registered_tool: RegisteredTool,
        runner: ExtensionRunner,
    ) -> None:
        self._registered_tool = registered_tool
        self._runner = runner
        self._definition = registered_tool["definition"]

    @property
    def name(self) -> str:
        return self._definition.get("name", "")

    @property
    def label(self) -> str:
        return self._definition.get("label", "")

    @property
    def description(self) -> str:
        return self._definition.get("description", "")

    @property
    def parameters(self) -> dict:
        return self._definition.get("parameters", {})

    @property
    def registered_tool(self) -> RegisteredTool:
        return self._registered_tool

    async def execute(
        self,
        tool_call_id: str,
        params: dict,
        signal: Optional[Any] = None,
        on_update: Optional[Callable[..., None]] = None,
        ctx: Optional[ExtensionContext] = None,
    ) -> Any:
        """Forward to the registered tool's
        ``execute`` coroutine. The OpenClaw
        source's ``wrapToolDefinition`` adds
        the runner's context; the Python port
        does the same (the host calls this
        method through the agent-core loop)."""
        execute = self._definition.get("execute")
        if execute is None:
            raise RuntimeError(
                f"Tool {self.name!r} is registered without an execute function"
            )
        # Build a fresh context from the runner
        # (the OpenClaw source's
        # `() => runner.createContext()` pattern).
        actual_ctx = ctx if ctx is not None else self._runner.create_context()
        return await execute(
            tool_call_id, params, signal, on_update, actual_ctx
        )


# ============================================================================
# Public API
# ============================================================================


def wrap_registered_tool(
    registered_tool: RegisteredTool,
    runner: ExtensionRunner,
) -> _RegisteredToolWrapper:
    """Wrap a single :class:`RegisteredTool`
    into a runtime-callable tool proxy.
    Mirrors ``wrapRegisteredTool``
    (``wrapper.ts:17-22``)."""
    return _RegisteredToolWrapper(registered_tool, runner)


def wrap_registered_tools(
    registered_tools: list[RegisteredTool],
    runner: ExtensionRunner,
) -> list[_RegisteredToolWrapper]:
    """Wrap all registered tools into
    runtime-callable tool proxies. Mirrors
    ``wrapRegisteredTools``
    (``wrapper.ts:28-35``)."""
    return [wrap_registered_tool(t, runner) for t in registered_tools]


__all__ = [
    "wrap_registered_tool",
    "wrap_registered_tools",
]
