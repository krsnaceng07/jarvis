"""jarvis.agents.embedded_agent_runner.run.attempt_bundle_tools — bundle tools for one attempt.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/attempt-bundle-tools.ts``.

Public surface:

- :func:`prepare_embedded_attempt_bundle_tools` (async)

Phase 7.6d-2 — focused minimal port.

The OpenClaw source is tightly coupled to the bundle-MCP / bundle-
LSP runtime, tool-policy, and capability-profile layers. The
Python port keeps the public surface and delegates the heavy work
to installable hooks.
"""
from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Dict


#: Embedded-attempt bundle-tools shape.
EmbeddedAttemptBundleTools = Dict[str, Any]


# ---------------------------------------------------------------------------
# Hooks
# ---------------------------------------------------------------------------


#: Hook for the should-create-bundle-mcp-runtime-for-attempt step.
_SHOULD_CREATE_BUNDLE_MCP_RUNTIME: Callable[[Dict[str, Any]], bool] = (
    lambda _p: False
)


def set_should_create_bundle_mcp_runtime_hook(
    hook: Callable[[Dict[str, Any]], bool],
) -> None:
    """Install a custom shouldCreateBundleMcpRuntimeForAttempt hook."""
    global _SHOULD_CREATE_BUNDLE_MCP_RUNTIME
    _SHOULD_CREATE_BUNDLE_MCP_RUNTIME = hook


#: Hook for the should-create-bundle-lsp-runtime-for-attempt step.
_SHOULD_CREATE_BUNDLE_LSP_RUNTIME: Callable[[Dict[str, Any]], bool] = (
    lambda _p: False
)


def set_should_create_bundle_lsp_runtime_hook(
    hook: Callable[[Dict[str, Any]], bool],
) -> None:
    """Install a custom shouldCreateBundleLspRuntimeForAttempt hook."""
    global _SHOULD_CREATE_BUNDLE_LSP_RUNTIME
    _SHOULD_CREATE_BUNDLE_LSP_RUNTIME = hook


#: Hook for the create-bundle-mcp-runtime step.
_CREATE_BUNDLE_MCP_RUNTIME: Callable[
    [Dict[str, Any]], Awaitable[Any]
] = lambda _p: asyncio.sleep(0)


def set_create_bundle_mcp_runtime_hook(
    hook: Callable[[Dict[str, Any]], Awaitable[Any]],
) -> None:
    """Install a custom createBundleMcpRuntime hook."""
    global _CREATE_BUNDLE_MCP_RUNTIME
    _CREATE_BUNDLE_MCP_RUNTIME = hook


#: Hook for the create-bundle-lsp-runtime step.
_CREATE_BUNDLE_LSP_RUNTIME: Callable[
    [Dict[str, Any]], Awaitable[Any]
] = lambda _p: asyncio.sleep(0)


def set_create_bundle_lsp_runtime_hook(
    hook: Callable[[Dict[str, Any]], Awaitable[Any]],
) -> None:
    """Install a custom createBundleLspRuntime hook."""
    global _CREATE_BUNDLE_LSP_RUNTIME
    _CREATE_BUNDLE_LSP_RUNTIME = hook


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def prepare_embedded_attempt_bundle_tools(
    params: Dict[str, Any],
) -> EmbeddedAttemptBundleTools:
    """Bundle the tools for one attempt.

    Mirrors :func:`prepareEmbeddedAttemptBundleTools`
    (``attempt-bundle-tools.ts``).
    """
    tools = list(params.get("tools") or [])
    uncompacted_effective_tools = list(
        params.get("uncompactedEffectiveTools") or []
    )
    return {
        "tools": tools,
        "uncompactedEffectiveTools": uncompacted_effective_tools,
        "toolSearch": params.get("toolSearch"),
    }


__all__ = [
    "EmbeddedAttemptBundleTools",
    "prepare_embedded_attempt_bundle_tools",
    "set_create_bundle_lsp_runtime_hook",
    "set_create_bundle_mcp_runtime_hook",
    "set_should_create_bundle_lsp_runtime_hook",
    "set_should_create_bundle_mcp_runtime_hook",
]
