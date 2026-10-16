"""jarvis.agents.embedded_agent_runner.tool_schema_runtime — provider tool-schema normalization.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/tool-schema-runtime.ts``.

Public surface (mirrors the OpenClaw source):

- :func:`normalize_provider_tool_schemas` — run provider-owned
  tool-schema normalization without encoding provider families
  in the embedded runner.
- :func:`log_provider_tool_schema_diagnostics` — log
  provider-owned tool-schema diagnostics after normalization.

Phase 7.4a — focused minimal port.

The OpenClaw source is tightly coupled to the provider-runtime
plugin, plugin-handle, and provider-tool-schema-inspector layers.
The Python port keeps the public surface but delegates the heavy
plugin normalization and inspection to installable hooks so the
host can plug in the real provider-runtime layer as it lands.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List


#: Normalize provider tool schemas hook. The host installs the
#: real :func:`normalizeProviderToolSchemasWithPlugin`` when the
#: provider-runtime layer lands. The default returns the input
#: tools unchanged.
_NORMALIZE_PROVIDER_TOOL_SCHEMAS_WITH_PLUGIN: Callable[..., Any] = (
    lambda **kwargs: kwargs.get("context", {}).get("tools")
)


def set_normalize_provider_tool_schemas_with_plugin_hook(
    hook: Callable[..., Any],
) -> None:
    """Install a custom normalize-provider-tool-schemas hook."""
    global _NORMALIZE_PROVIDER_TOOL_SCHEMAS_WITH_PLUGIN
    _NORMALIZE_PROVIDER_TOOL_SCHEMAS_WITH_PLUGIN = hook


#: Inspect provider tool schemas hook. The host installs the
#: real :func:`inspectProviderToolSchemasWithPlugin`` when the
#: provider-runtime layer lands. The default returns an empty
#: list.
_INSPECT_PROVIDER_TOOL_SCHEMAS_WITH_PLUGIN: Callable[..., List[Dict[str, Any]]] = (
    lambda **_kwargs: []
)


def set_inspect_provider_tool_schemas_with_plugin_hook(
    hook: Callable[..., List[Dict[str, Any]]],
) -> None:
    """Install a custom inspect-provider-tool-schemas hook."""
    global _INSPECT_PROVIDER_TOOL_SCHEMAS_WITH_PLUGIN
    _INSPECT_PROVIDER_TOOL_SCHEMAS_WITH_PLUGIN = hook


def _build_provider_tool_schema_context(
    params: Dict[str, Any],
    provider: str,
) -> Dict[str, Any]:
    """Build the provider tool-schema context.

    Mirrors :func:`buildProviderToolSchemaContext``
    (``tool-schema-runtime.ts:30-44``).
    """
    return {
        "config": params.get("config"),
        "workspaceDir": params.get("workspaceDir"),
        "env": params.get("env"),
        "provider": provider,
        "modelId": params.get("modelId"),
        "modelApi": params.get("modelApi"),
        "model": params.get("model"),
        "tools": params.get("tools") or [],
    }


def normalize_provider_tool_schemas(
    params: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Run provider-owned tool-schema normalization.

    Mirrors :func:`normalizeProviderToolSchemas``
    (``tool-schema-runtime.ts:50-67``).
    """
    provider = (params.get("provider") or "").strip()
    context = _build_provider_tool_schema_context(params, provider)
    normalized = _NORMALIZE_PROVIDER_TOOL_SCHEMAS_WITH_PLUGIN(
        provider=provider,
        config=params.get("config"),
        workspaceDir=params.get("workspaceDir"),
        env=params.get("env"),
        runtimeHandle=params.get("runtimeHandle"),
        allowRuntimePluginLoad=params.get("allowRuntimePluginLoad"),
        context=context,
    )
    if isinstance(normalized, list):
        return list(normalized)
    return list(params.get("tools") or [])


def _summarize_provider_tool_schema_diagnostics(
    diagnostics: List[Dict[str, Any]],
) -> str:
    """Summarize the diagnostics for the log line.

    Mirrors :func:`summarizeProviderToolSchemaDiagnostics``
    (``tool-schema-runtime.ts:108-116``).
    """
    visible = diagnostics[:6]
    parts: List[str] = []
    for diagnostic in visible:
        violations = diagnostic.get("violations") or []
        violation_count = len(violations)
        tool_name = diagnostic.get("toolName") or "unknown"
        label = "violation" if violation_count == 1 else "violations"
        parts.append(f"{tool_name} ({violation_count} {label})")
    remaining = len(diagnostics) - len(visible)
    summary = ", ".join(parts)
    if remaining > 0:
        summary = f"{summary}, +{remaining} more" if summary else f"+{remaining} more"
    return summary


def log_provider_tool_schema_diagnostics(
    params: Dict[str, Any],
) -> None:
    """Log provider-owned tool-schema diagnostics.

    Mirrors :func:`logProviderToolSchemaDiagnostics``
    (``tool-schema-runtime.ts:72-106``).
    """
    provider = (params.get("provider") or "").strip()
    context = _build_provider_tool_schema_context(params, provider)
    diagnostics = _INSPECT_PROVIDER_TOOL_SCHEMAS_WITH_PLUGIN(
        provider=provider,
        config=params.get("config"),
        workspaceDir=params.get("workspaceDir"),
        env=params.get("env"),
        runtimeHandle=params.get("runtimeHandle"),
        allowRuntimePluginLoad=params.get("allowRuntimePluginLoad"),
        context=context,
    )
    if not isinstance(diagnostics, list) or not diagnostics:
        return
    summary = _summarize_provider_tool_schema_diagnostics(diagnostics)
    from .logger import log

    tools = params.get("tools") or []
    log.warning(
        f"provider tool schema diagnostics: {len(diagnostics)} "
        f"{'tool' if len(diagnostics) == 1 else 'tools'} for {params.get('provider', '')}: {summary}",
        {
            "provider": params.get("provider", ""),
            "toolCount": len(tools),
            "diagnosticCount": len(diagnostics),
            "tools": [f"{index}:{tool.get('name', '')}" for index, tool in enumerate(tools)],
            "diagnostics": [
                {
                    "index": diagnostic.get("toolIndex"),
                    "tool": diagnostic.get("toolName"),
                    "violations": (diagnostic.get("violations") or [])[:12],
                    "violationCount": len(diagnostic.get("violations") or []),
                }
                for diagnostic in diagnostics
            ],
        },
    )


__all__ = [
    "log_provider_tool_schema_diagnostics",
    "normalize_provider_tool_schemas",
    "set_inspect_provider_tool_schemas_with_plugin_hook",
    "set_normalize_provider_tool_schemas_with_plugin_hook",
]
