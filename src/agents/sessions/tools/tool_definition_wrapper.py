"""jarvis.agents.sessions.tools.tool_definition_wrapper — tool definition/AgentTool adapters.

OpenClaw parity: mirrors
``openclaw-main/src/agents/sessions/tools/tool-definition-wrapper.ts``.

Phase 6.10b — bridges extension-style
:class:`ToolDefinition` objects and the
core runtime ``AgentTool`` shape.

Adaptations
-----------
- The OpenClaw source wraps a TypeBox
  ``TSchema`` for ``parameters`` /
  ``outputSchema``. The Python port uses
  plain :class:`dict` (TypeBox equivalent
  lands in Phase 6.10+ with the tool
  contracts).
- The OpenClaw source's ``AgentTool`` is a
  TypeBox-typed object literal. The Python
  port returns a ``dict``-shaped tool proxy
  with the same field set; the actual
  ``AgentTool`` runtime class lands in
  Phase 6.12 alongside the agent loop
  integration.
- The ``wrapToolDefinition`` factory accepts
  a ``ctxFactory()`` callable that returns
  the ``ExtensionContext`` for the call.
  The Python port preserves this contract.
- ``createToolDefinitionFromAgentTool``
  reverses the direction — synthesises a
  ``ToolDefinition`` from an ``AgentTool``
  so the session registry can stay
  definition-first.
"""
from __future__ import annotations

from typing import Any, Callable, Optional

from ..extensions.types import ExtensionContext, ToolDefinition


#: An AgentTool is a runtime-callable tool.
#: The full shape lands in Phase 6.12 with
#: the agent-core integration; the Python
#: port uses a ``dict`` shape with the same
#: fields as the OpenClaw source.
AgentTool = dict


def wrap_tool_definition(
    definition: ToolDefinition,
    ctx_factory: Optional[Callable[[], ExtensionContext]] = None,
) -> AgentTool:
    """Wrap a :class:`ToolDefinition` into an
    :data:`AgentTool` for the core runtime.
    Mirrors ``wrapToolDefinition``
    (``tool-definition-wrapper.ts:11-31``)."""
    agent_tool: dict = {
        "name": definition.get("name", ""),
        "label": definition.get("label", ""),
        "description": definition.get("description", ""),
    }
    if definition.get("hideFromChannelProgress") is True:
        agent_tool["hideFromChannelProgress"] = True
    if "parameters" in definition:
        agent_tool["parameters"] = definition["parameters"]
    if "outputSchema" in definition:
        agent_tool["outputSchema"] = definition["outputSchema"]
    if "prepareArguments" in definition:
        agent_tool["prepareArguments"] = definition["prepareArguments"]
    if "executionMode" in definition:
        agent_tool["executionMode"] = definition["executionMode"]
    # The execute closure calls the
    # definition's execute with the lazily
    # built context (matches the OpenClaw
    # source's ``ctxFactory?.()`` call).
    raw_execute = definition.get("execute")
    if raw_execute is not None:

        async def _execute(
            tool_call_id: str,
            params: Any,
            signal: Any,
            on_update: Any,
        ) -> Any:
            ctx = ctx_factory() if ctx_factory is not None else None
            return await raw_execute(
                tool_call_id, params, signal, on_update, ctx
            )

        agent_tool["execute"] = _execute
    else:
        async def _no_execute(
            *args: Any, **kwargs: Any
        ) -> Any:
            raise RuntimeError(
                f"Tool {definition.get('name', '<unnamed>')!r} "
                "has no execute() function"
            )

        agent_tool["execute"] = _no_execute
    return agent_tool


def wrap_tool_definitions(
    definitions: list[ToolDefinition],
    ctx_factory: Optional[Callable[[], ExtensionContext]] = None,
) -> list[AgentTool]:
    """Wrap multiple ``ToolDefinition`` objects
    into :data:`AgentTool` proxies. Mirrors
    ``wrapToolDefinitions``
    (``tool-definition-wrapper.ts:33-39``)."""
    return [wrap_tool_definition(d, ctx_factory) for d in definitions]


def create_tool_definition_from_agent_tool(tool: AgentTool) -> ToolDefinition:
    """Synthesise a minimal :class:`ToolDefinition`
    from an :data:`AgentTool`. Mirrors
    ``createToolDefinitionFromAgentTool``
    (``tool-definition-wrapper.ts:47-60``).

    The Python port is useful for AgentSession's
    definition-first registry even when a
    caller provides a plain AgentTool that
    lacks prompt metadata or renderers.
    """
    raw_execute = tool.get("execute")
    if raw_execute is None:
        raise RuntimeError(
            f"AgentTool {tool.get('name', '<unnamed>')!r} "
            "has no execute() function"
        )

    async def _execute(
        tool_call_id: str,
        params: Any,
        signal: Any,
        on_update: Any,
        ctx: Any,
    ) -> Any:
        # The Python port ignores ``ctx`` (the
        # AgentTool's execute signature does
        # not take a context — the OpenClaw
        # source has the same arity).
        return await raw_execute(
            tool_call_id, params, signal, on_update
        )

    definition: dict = {
        "name": tool.get("name", ""),
        "label": tool.get("label", ""),
        "description": tool.get("description", ""),
        "parameters": tool.get("parameters", {}),
        "execute": _execute,
    }
    if tool.get("hideFromChannelProgress") is True:
        definition["hideFromChannelProgress"] = True
    if "outputSchema" in tool:
        definition["outputSchema"] = tool["outputSchema"]
    if "prepareArguments" in tool:
        definition["prepareArguments"] = tool["prepareArguments"]
    if "executionMode" in tool:
        definition["executionMode"] = tool["executionMode"]
    return definition  # type: ignore[return-value]


__all__ = [
    "AgentTool",
    "create_tool_definition_from_agent_tool",
    "wrap_tool_definition",
    "wrap_tool_definitions",
]
