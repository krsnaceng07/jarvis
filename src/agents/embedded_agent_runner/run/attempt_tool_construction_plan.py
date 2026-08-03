"""jarvis.agents.embedded_agent_runner.run.attempt_tool_construction_plan — resolve the tool-construction plan for an attempt.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/attempt-tool-construction-plan.ts``.

Public surface:

Functions:

- :func:`apply_embedded_attempt_tools_allow`
- :func:`merge_forced_embedded_attempt_tools_allow`
- :func:`resolve_embedded_attempt_tool_construction_plan`
- :func:`should_create_bundle_mcp_runtime_for_attempt`
- :func:`should_create_bundle_lsp_runtime_for_attempt`

Phase 7.6d-2 — focused minimal port.

The OpenClaw source is tightly coupled to the tool-policy,
tool-allowlist, capability-profile, and effective-tool-policy
layers. The Python port keeps the public surface and delegates
the heavy work to installable hooks.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, TypeVar


T = TypeVar("T", bound=Dict[str, Any])


#: Embedded-attempt tool-construction plan.
EmbeddedAttemptToolConstructionPlan = Dict[str, Any]


# ---------------------------------------------------------------------------
# Pure helpers (ported as-is)
# ---------------------------------------------------------------------------


def apply_embedded_attempt_tools_allow(
    tools: List[T],
    allow: Optional[List[str]],
) -> List[T]:
    """Filter ``tools`` to those whose ``name`` is in ``allow``.

    Mirrors :func:`applyEmbeddedAttemptToolsAllow`
    (``attempt-tool-construction-plan.ts``).
    """
    if not isinstance(tools, list):
        return []
    if not allow:
        return list(tools)
    allow_set = {str(name) for name in allow if isinstance(name, str)}
    return [tool for tool in tools if (tool or {}).get("name") in allow_set]


def merge_forced_embedded_attempt_tools_allow(
    allow_lists: List[Optional[List[str]]],
) -> List[str]:
    """Merge multiple allow lists into one deduplicated list.

    Mirrors :func:`mergeForcedEmbeddedAttemptToolsAllow`
    (``attempt-tool-construction-plan.ts``).
    """
    merged: List[str] = []
    seen: set = set()
    for allow in allow_lists or []:
        if not isinstance(allow, list):
            continue
        for name in allow:
            if not isinstance(name, str) or not name:
                continue
            if name in seen:
                continue
            seen.add(name)
            merged.append(name)
    return merged


# ---------------------------------------------------------------------------
# Hooks
# ---------------------------------------------------------------------------


#: Hook for the should-create-bundle-mcp-runtime step.
_SHOULD_CREATE_BUNDLE_MCP_RUNTIME: Callable[[Dict[str, Any]], bool] = (
    lambda _p: False
)


def set_should_create_bundle_mcp_runtime_construction_hook(
    hook: Callable[[Dict[str, Any]], bool],
) -> None:
    """Install a custom shouldCreateBundleMcpRuntimeForAttempt hook."""
    global _SHOULD_CREATE_BUNDLE_MCP_RUNTIME
    _SHOULD_CREATE_BUNDLE_MCP_RUNTIME = hook


#: Hook for the should-create-bundle-lsp-runtime step.
_SHOULD_CREATE_BUNDLE_LSP_RUNTIME: Callable[[Dict[str, Any]], bool] = (
    lambda _p: False
)


def set_should_create_bundle_lsp_runtime_construction_hook(
    hook: Callable[[Dict[str, Any]], bool],
) -> None:
    """Install a custom shouldCreateBundleLspRuntimeForAttempt hook."""
    global _SHOULD_CREATE_BUNDLE_LSP_RUNTIME
    _SHOULD_CREATE_BUNDLE_LSP_RUNTIME = hook


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def resolve_embedded_attempt_tool_construction_plan(
    params: Dict[str, Any],
) -> EmbeddedAttemptToolConstructionPlan:
    """Resolve the tool-construction plan for an attempt.

    Mirrors :func:`resolveEmbeddedAttemptToolConstructionPlan`
    (``attempt-tool-construction-plan.ts``).
    """
    allow_lists = params.get("allowLists") or []
    runtime_allow = params.get("runtimeAllow")
    merged_allow = merge_forced_embedded_attempt_tools_allow(
        [*(allow_lists if isinstance(allow_lists, list) else []), runtime_allow]
    )
    return {
        "toolsAllow": merged_allow,
        "shouldCreateBundleMcpRuntime": _SHOULD_CREATE_BUNDLE_MCP_RUNTIME(
            dict(params or {})
        ),
        "shouldCreateBundleLspRuntime": _SHOULD_CREATE_BUNDLE_LSP_RUNTIME(
            dict(params or {})
        ),
    }


def should_create_bundle_mcp_runtime_for_attempt(
    params: Dict[str, Any],
) -> bool:
    """Return True when the attempt should create a bundle-MCP runtime.

    Mirrors :func:`shouldCreateBundleMcpRuntimeForAttempt`
    (``attempt-tool-construction-plan.ts``).
    """
    return _SHOULD_CREATE_BUNDLE_MCP_RUNTIME(dict(params or {}))


def should_create_bundle_lsp_runtime_for_attempt(
    params: Dict[str, Any],
) -> bool:
    """Return True when the attempt should create a bundle-LSP runtime.

    Mirrors :func:`shouldCreateBundleLspRuntimeForAttempt`
    (``attempt-tool-construction-plan.ts``).
    """
    return _SHOULD_CREATE_BUNDLE_LSP_RUNTIME(dict(params or {}))


__all__ = [
    "EmbeddedAttemptToolConstructionPlan",
    "apply_embedded_attempt_tools_allow",
    "merge_forced_embedded_attempt_tools_allow",
    "resolve_embedded_attempt_tool_construction_plan",
    "set_should_create_bundle_lsp_runtime_construction_hook",
    "set_should_create_bundle_mcp_runtime_construction_hook",
    "should_create_bundle_lsp_runtime_for_attempt",
    "should_create_bundle_mcp_runtime_for_attempt",
]
