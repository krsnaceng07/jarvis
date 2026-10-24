"""Effective tool inventory — one declared-and-executable tool surface.

OpenClaw parity: mirrors ``openclaw-main/src/agents/tools-effective-inventory.ts``
and the admission rules in ``tool-surface-plan.ts``.

Invariant enforced here: every declared tool is executable, and every executable
tool is declared. The live surfaces used to assemble declarations and dispatch
tables separately, so the channel and desktop engines declared 42/24 tools while
holding 46+ executors; the model never saw tools such as ``image_generate`` and
fell back to chat. One owner removes that class of drift.
"""

from __future__ import annotations

import inspect
import json
import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Iterable, Mapping, Sequence

from .tool_policy import filter_tools_by_policy

_log = logging.getLogger("jarvis.agents.tools_effective_inventory")

#: Executor call shape: ``(args, call_id) -> str | dict | AgentToolResult``.
ToolExecutor = Callable[[dict[str, Any], str], Awaitable[Any]]


@dataclass(frozen=True, slots=True)
class ToolEntry:
    """A model-facing declaration plus the executor bound to it."""

    name: str
    description: str
    parameters: dict[str, Any]
    source: str
    execute: ToolExecutor


@dataclass(frozen=True, slots=True)
class ToolInvocation:
    """Outcome of one tool call, shaped for direct model feedback."""

    name: str
    ok: bool
    output: str
    error: str | None = None

    @property
    def result_text(self) -> str:
        if self.ok:
            return self.output
        return f"Tool '{self.name}' failed: {self.error}"


class ToolSurface:
    """Ordered, immutable view of the tools admitted for one live surface."""

    __slots__ = ("_entries",)

    def __init__(self, entries: Mapping[str, ToolEntry]) -> None:
        self._entries: dict[str, ToolEntry] = dict(entries)

    def __len__(self) -> int:
        return len(self._entries)

    def __contains__(self, name: object) -> bool:
        return name in self._entries

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(self._entries)

    @property
    def entries(self) -> tuple[ToolEntry, ...]:
        return tuple(self._entries.values())

    def declarations(self) -> list[dict[str, Any]]:
        """Model-facing declarations, in stable inventory order."""
        return [
            {
                "name": entry.name,
                "description": entry.description,
                "parameters": entry.parameters,
            }
            for entry in self._entries.values()
        ]

    def get(self, name: str) -> ToolEntry | None:
        return self._entries.get(name)

    async def invoke(
        self,
        name: str,
        args: Mapping[str, Any] | None = None,
        call_id: str = "call",
    ) -> ToolInvocation:
        """Execute one admitted tool. Never raises; failures travel as results."""
        entry = self._entries.get(name)
        if entry is None:
            return ToolInvocation(
                name=name,
                ok=False,
                output="",
                error=(
                    "not available in this surface. Call only the declared tools; "
                    "if the capability is missing, say so instead of claiming success."
                ),
            )
        try:
            raw = await entry.execute(dict(args or {}), call_id)
        except Exception as exc:  # noqa: BLE001 - tool failures become model feedback
            _log.warning("Tool %s failed: %s", name, exc)
            return ToolInvocation(name=name, ok=False, output="", error=_describe_error(exc))
        return ToolInvocation(name=name, ok=True, output=_stringify_output(raw))


async def invoke_host_tool(tool: Any, args: Mapping[str, Any], call_id: str = "call") -> Any:
    """Run one raw host ``AgentTool`` dict by its own arity contract."""
    execute = _host_executor(tool)
    if execute is None:
        raise RuntimeError("host tool has no execute handler")
    return await execute(dict(args), call_id)


def build_effective_tool_inventory(
    *,
    base_declarations: Sequence[Mapping[str, Any]] = (),
    plugin_tools: Sequence[Mapping[str, Any]] = (),
    plugin_dispatch: Mapping[str, Any] | None = None,
    host_tools: Mapping[str, Any] | None = None,
    control_executors: Mapping[str, ToolExecutor] | None = None,
    executor_overrides: Mapping[str, ToolExecutor] | None = None,
    allow: Sequence[str] | None = None,
    deny: Sequence[str] | None = None,
) -> ToolSurface:
    """Merge base, plugin, and host tools into one executable surface.

    Schema precedence is ``base > plugin > host`` (a core declaration such as
    ``browser`` keeps its curated wording). Executor precedence is
    ``override > plugin > host > control``; overrides exist for surfaces that
    must bind one tool to a host-owned implementation that supersedes a plugin
    (for example the voice engine owning ``computer``).
    """
    dispatch = plugin_dispatch or {}
    hosts = host_tools or {}
    controls = control_executors or {}
    overrides = executor_overrides or {}

    executors: dict[str, ToolExecutor] = {}
    controls_entries = dict(controls)
    executors.update(controls_entries)
    for name, tool in hosts.items():
        execute = _host_executor(tool)
        if execute is not None:
            executors[name] = execute
    for name, binding in dispatch.items():
        execute = _plugin_executor(binding)
        if execute is not None:
            executors[name] = execute
    executors.update(overrides)

    declarations: dict[str, dict[str, Any]] = {}
    for decl in base_declarations:
        _remember(declarations, decl, "core")
    for decl in plugin_tools:
        _remember(declarations, decl, "plugin")
    for name, tool in hosts.items():
        decl = _host_declaration(tool, name)
        if decl is not None:
            _remember(declarations, decl, "host")

    entries: dict[str, ToolEntry] = {}
    for name, decl in declarations.items():
        execute = executors.get(name)
        if execute is None:
            _log.debug("Tool %r declared without an executor; omitted from surface", name)
            continue
        entries[name] = ToolEntry(
            name=name,
            description=decl["description"],
            parameters=decl["parameters"],
            source=decl["source"],
            execute=execute,
        )

    for name in executors:
        if name not in entries:
            _log.debug("Tool %r executable but undeclared; omitted from surface", name)

    if allow or deny:
        allowed = filter_tools_by_policy(list(entries), allow=allow, deny=deny)
        entries = {name: entries[name] for name in allowed}

    return ToolSurface(entries)


def _remember(target: dict[str, dict[str, Any]], decl: Mapping[str, Any], source: str) -> None:
    name = str(decl.get("name") or "").strip()
    if not name or name in target:
        return
    raw_params = decl.get("parameters")
    target[name] = {
        "description": _describe(decl.get("description")),
        "parameters": raw_params
        if isinstance(raw_params, dict)
        else {"type": "object", "properties": {}},
        "source": source,
    }


def _describe(value: Any) -> str:
    if isinstance(value, (list, tuple)):
        return " ".join(str(item) for item in value)
    return str(value or "")


def _host_declaration(tool: Any, fallback_name: str) -> dict[str, Any] | None:
    decl = (
        getattr(tool, "declaration", None)
        or getattr(tool, "schema", None)
        or getattr(tool, "tool_declaration", None)
    )
    if isinstance(decl, dict) and "name" in decl:
        return decl
    if isinstance(tool, dict) and "name" in tool:
        name = str(tool.get("name") or fallback_name)
        params = tool.get("parameters") or tool.get("inputSchema")
        return {
            "name": name,
            "description": _describe(tool.get("description")),
            "parameters": params
            if isinstance(params, dict)
            else {"type": "object", "properties": {}},
        }
    return None


def _call_arity(fn: Any) -> int:
    try:
        signature = inspect.signature(fn)
    except (TypeError, ValueError):
        return 2
    positional = [
        parameter
        for parameter in signature.parameters.values()
        if parameter.kind
        in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
    ]
    return len(positional)


def _host_executor(tool: Any) -> ToolExecutor | None:
    if not isinstance(tool, dict):
        return None
    fn = tool.get("execute")
    if not callable(fn):
        return None
    arity = _call_arity(fn)

    async def run(args: dict[str, Any], call_id: str) -> Any:
        if arity <= 1:
            result: Any = fn(args)
        elif arity == 2:
            result = fn(call_id, args)
        elif arity == 3:
            result = fn(call_id, args, None)
        elif arity == 4:
            result = fn(call_id, args, None, None)
        else:
            result = fn(call_id, args, None, None, None)
        if inspect.isawaitable(result):
            result = await result
        return result

    return run


def _plugin_executor(binding: Any) -> ToolExecutor | None:
    try:
        plugin_inst, call_name = binding
    except (TypeError, ValueError):
        return None
    if not callable(getattr(plugin_inst, "call", None)):
        return None

    async def run(args: dict[str, Any], call_id: str) -> Any:
        result: Any = plugin_inst.call(call_name, args)
        if inspect.isawaitable(result):
            result = await result
        return result

    return run


def _stringify_output(value: Any) -> str:
    if value is None:
        return "Done."
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        content = value.get("content")
        if isinstance(content, list) and content:
            parts: list[str] = []
            for item in content:
                if isinstance(item, dict) and "text" in item:
                    parts.append(str(item["text"]))
                elif isinstance(item, str):
                    parts.append(item)
            if parts:
                return "\n".join(parts)
        for key in ("text", "result", "output"):
            if key in value:
                return str(value[key])
        return json.dumps(value, ensure_ascii=False, default=str)
    unwrapped = _unwrap_sdk_result(value)
    if unwrapped is not None:
        return unwrapped
    return str(value)


def _unwrap_sdk_result(value: Any) -> str | None:
    try:
        from jarvis_sdk import Err, Ok
    except Exception:
        return None
    if isinstance(value, Ok):
        return value.value if isinstance(value.value, str) else str(value.value)
    if isinstance(value, Err):
        return f"Error: {value.error}"
    return None


def _describe_error(exc: BaseException) -> str:
    message = str(exc).strip()
    return f"{type(exc).__name__}: {message}" if message else type(exc).__name__


def _iter_entries(surface: ToolSurface) -> Iterable[ToolEntry]:
    return surface.entries


__all__ = [
    "ToolEntry",
    "ToolExecutor",
    "ToolInvocation",
    "ToolSurface",
    "build_effective_tool_inventory",
    "invoke_host_tool",
    "_stringify_output",
]
