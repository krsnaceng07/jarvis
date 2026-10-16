"""jarvis_sdk.tool_plugin — Tool-only plugin builder (`define_tool_plugin`).

OpenClaw parity: mirrors
``openclaw-main/src/plugin-sdk/tool-plugin.ts``.

Features:
- `ToolPluginToolDefinition`: Dataclass defining a tool-only plugin tool.
- `ToolPluginDefinition`: Dataclass defining a tool plugin entry.
- `define_tool_plugin()`: Helper for declaring tool-only plugins without standard boilerplate.
- Automatic return value wrapping: Converts str to text result dicts, dicts to structured JSON details dicts.
"""

from __future__ import annotations

import inspect
import json
from dataclasses import dataclass, field
from typing import Any, Callable

from .plugin_entry import JarvisPluginApi, PluginEntryDefinition


@dataclass
class ToolPluginToolDefinition:
    name: str
    description: str
    parameters: dict[str, Any]
    execute: Callable[..., Any]
    label: str | None = None
    outputSchema: dict[str, Any] | None = None
    optional: bool = False


@dataclass
class ToolPluginDefinition(PluginEntryDefinition):
    configSchema: dict[str, Any] = field(default_factory=dict)
    declared_tools: list[ToolPluginToolDefinition] = field(default_factory=list)

    @property
    def register_fn(self) -> Callable[[Any], None]:
        return self.register


def format_tool_result(res: Any) -> dict[str, Any]:
    """Wrap raw tool execution returns into canonical tool result format."""
    if isinstance(res, str):
        return {"content": [{"type": "text", "text": res}], "details": res}
    if isinstance(res, dict) and "content" in res:
        return res
    details = res
    text = json.dumps(res, indent=2, ensure_ascii=False, default=str)
    return {"content": [{"type": "text", "text": text}], "details": details}


def define_tool_plugin(
    id: str,
    name: str,
    description: str,
    tools: Callable[[Callable[..., ToolPluginToolDefinition]], list[ToolPluginToolDefinition]],
    config_schema: dict[str, Any] | None = None,
) -> ToolPluginDefinition:
    """Define a tool-only plugin with automatic tool registration and manifest contracts."""

    def tool_factory(
        name: str,
        description: str,
        parameters: dict[str, Any],
        execute: Callable[..., Any],
        label: str | None = None,
        output_schema: dict[str, Any] | None = None,
        optional: bool = False,
    ) -> ToolPluginToolDefinition:
        return ToolPluginToolDefinition(
            name=name,
            description=description,
            parameters=parameters,
            execute=execute,
            label=label or name,
            outputSchema=output_schema,
            optional=optional,
        )

    declared_tools = tools(tool_factory)

    def register_fn(api: JarvisPluginApi) -> None:
        for t in declared_tools:

            async def make_wrapper(func: Callable[..., Any], args: Any):
                val = func(args)
                if inspect.isawaitable(val):
                    val = await val
                return format_tool_result(val)

            def create_exec(target_func: Callable[..., Any]):
                async def exec_impl(_id: str, params: dict[str, Any]):
                    return await make_wrapper(target_func, params)

                return exec_impl

            api.register_tool(
                name=t.name,
                description=t.description,
                parameters=t.parameters,
                execute=create_exec(t.execute),
                output_schema=t.outputSchema,
                optional=t.optional,
            )

    return ToolPluginDefinition(
        id=id,
        name=name,
        description=description,
        kind="standard",
        register=register_fn,
        configSchema=config_schema or {},
        declared_tools=declared_tools,
    )


__all__ = [
    "ToolPluginDefinition",
    "ToolPluginToolDefinition",
    "define_tool_plugin",
    "format_tool_result",
]
