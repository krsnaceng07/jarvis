"""Tool dispatch bridge — routes LLM tool_calls to plugin dispatch functions.

Mirrors OpenClaw's ``src/tools/dispatch.ts`` +
``src/tools/tool-registry.ts``.

The ``ToolDispatcher`` is the host-side component that:
  1. Holds a snapshot of the plugin tool dispatch table (from ``LoadResult``).
  2. When the LLM returns tool_call(s), routes each to the right plugin's
     ``call(tool_name, args)`` function.
  3. Returns a ``ToolCallResult`` per call — success with a value, or an
     error result the LLM can reason about.

Architecture note: the LLM does NOT call tools directly. It proposes
tool_calls in its output; the agent loop collects them, calls
``ToolDispatcher.execute()`` for each, and injects the results back as
``ToolResultMessage`` items in the next turn. This is the OpenClaw
``AgentTool.execute`` pattern, ported to JARVIS's plugin_dispatch dict.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

_log = logging.getLogger("jarvis.tools.dispatch")

# Plugin dispatch fn: (tool_name: str, args: dict) -> Any
PluginDispatchFn = Callable[[str, dict[str, Any]], Any]


# ── Result types ───────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class ToolCallResult:
    """The normalized result of a single tool call.

    Mirrors OpenClaw's ``AgentToolResult`` from ``src/agent/types.ts``.

    Attributes
    ----------
    tool_name : str
        The tool that was called.
    call_id : str
        The LLM-supplied tool_call_id (used to correlate results).
    content : str
        The result as a text string (JSON, markdown, or plain text).
    is_error : bool
        True when the call failed. The LLM sees the error text and can
        retry or ask for clarification.
    duration_ms : int
        Elapsed time in milliseconds.
    """

    tool_name: str
    call_id: str
    content: str
    is_error: bool = False
    duration_ms: int = 0


# ── Dispatcher ─────────────────────────────────────────────────────────


class ToolDispatcher:
    """Routes LLM tool_calls to plugin dispatch functions.

    Mirrors OpenClaw's ``ToolRegistry`` from
    ``src/tools/tool-registry.ts``.

    Instantiated once per host startup with the ``plugin_dispatch`` dict
    from ``LoadResult``. The dispatch dict maps tool names to
    ``(tool_name, args) -> result`` callables.

    Phase W2: sync dispatch only. Async tool calls land in Wave 3 when
    the full ``AgentTool.execute`` async contract is connected.
    """

    def __init__(self, plugin_dispatch: dict[str, PluginDispatchFn]) -> None:
        # Clone to avoid mutation after construction.
        self._dispatch = dict(plugin_dispatch)
        _log.info(
            "tool_dispatcher: registered %d tool(s): %s",
            len(self._dispatch),
            list(self._dispatch),
        )

    def has(self, tool_name: str) -> bool:
        """Return True if ``tool_name`` is registered."""
        return tool_name in self._dispatch

    def registered_names(self) -> list[str]:
        """Return all registered tool names."""
        return list(self._dispatch)

    def execute(
        self,
        tool_name: str,
        args: dict[str, Any],
        *,
        call_id: str = "",
    ) -> ToolCallResult:
        """Execute a single tool call synchronously.

        Parameters
        ----------
        tool_name : str
            The name of the tool to call (from the LLM's tool_call).
        args : dict[str, Any]
            The arguments provided by the LLM.
        call_id : str
            The LLM-supplied call_id for correlation.

        Returns
        -------
        ToolCallResult
            Never raises — errors are captured and returned as
            ``is_error=True`` results so the LLM can reason about them.
        """
        start = time.monotonic()
        fn = self._dispatch.get(tool_name)
        if fn is None:
            elapsed = int((time.monotonic() - start) * 1000)
            _log.warning("tool_dispatcher: unknown tool %r", tool_name)
            return ToolCallResult(
                tool_name=tool_name,
                call_id=call_id,
                content=f"Error: unknown tool '{tool_name}'. Available: {list(self._dispatch)}",
                is_error=True,
                duration_ms=elapsed,
            )

        try:
            result = fn(tool_name, args)
            elapsed = int((time.monotonic() - start) * 1000)
            # Normalize result to string.
            if result is None:
                content = "ok"
            elif isinstance(result, str):
                content = result
            else:
                import json
                try:
                    content = json.dumps(result, ensure_ascii=False, default=str)
                except (TypeError, ValueError):
                    content = str(result)

            _log.debug(
                "tool_dispatcher: %s completed in %dms",
                tool_name,
                elapsed,
            )
            return ToolCallResult(
                tool_name=tool_name,
                call_id=call_id,
                content=content,
                is_error=False,
                duration_ms=elapsed,
            )

        except Exception as exc:  # noqa: BLE001
            elapsed = int((time.monotonic() - start) * 1000)
            _log.warning("tool_dispatcher: %s raised: %s", tool_name, exc)
            return ToolCallResult(
                tool_name=tool_name,
                call_id=call_id,
                content=f"Error: {type(exc).__name__}: {exc}",
                is_error=True,
                duration_ms=elapsed,
            )

    def execute_batch(
        self,
        calls: list[dict[str, Any]],
    ) -> list[ToolCallResult]:
        """Execute a batch of tool calls.

        ``calls`` is a list of dicts with keys:
          - ``name`` (str)  — tool name
          - ``args`` (dict) — tool arguments
          - ``id`` (str)    — call_id (optional)

        Returns results in the same order as ``calls``.
        """
        return [
            self.execute(
                c.get("name", ""),
                c.get("args", {}),
                call_id=c.get("id", ""),
            )
            for c in calls
        ]


__all__ = ["PluginDispatchFn", "ToolCallResult", "ToolDispatcher"]
