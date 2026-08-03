"""jarvis.agents.embedded_agent_runner.run.attempt_subscription_cleanup — build subscription params and cleanup resources for an attempt.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/attempt.subscription-cleanup.ts``.

Public surface:

Functions:

- :func:`build_embedded_subscription_params`
- :func:`cleanup_embedded_attempt_resources` (async)

Phase 7.6d-7 — focused minimal port.
"""
from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Dict, List, Optional


#: Embedded subscription params shape.
EmbeddedSubscriptionParams = Dict[str, Any]


#: Embedded-attempt resources cleanup shape.
EmbeddedAttemptResourcesCleanup = Dict[str, Any]


#: Installable hook for the build-embedded-subscription-params step.
_BUILD_EMBEDDED_SUBSCRIPTION_PARAMS: Callable[
    [Dict[str, Any]], Any
] = lambda _p: {}


def set_build_embedded_subscription_params_hook(
    hook: Callable[[Dict[str, Any]], Any],
) -> None:
    """Install a custom buildEmbeddedSubscriptionParams hook."""
    global _BUILD_EMBEDDED_SUBSCRIPTION_PARAMS
    _BUILD_EMBEDDED_SUBSCRIPTION_PARAMS = hook


#: Installable hook for the cleanup-embedded-attempt-resources step.
_CLEANUP_EMBEDDED_ATTEMPT_RESOURCES: Callable[
    [Dict[str, Any]], Awaitable[Any]
] = lambda _p: asyncio.sleep(0)


def set_cleanup_embedded_attempt_resources_hook(
    hook: Callable[[Dict[str, Any]], Awaitable[Any]],
) -> None:
    """Install a custom cleanupEmbeddedAttemptResources hook."""
    global _CLEANUP_EMBEDDED_ATTEMPT_RESOURCES
    _CLEANUP_EMBEDDED_ATTEMPT_RESOURCES = hook


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_embedded_subscription_params(
    params: Dict[str, Any],
) -> EmbeddedSubscriptionParams:
    """Build the embedded subscription params.

    Mirrors :func:`buildEmbeddedSubscriptionParams`
    (``attempt.subscription-cleanup.ts``).
    """
    built = _BUILD_EMBEDDED_SUBSCRIPTION_PARAMS(dict(params or {}))
    if not isinstance(built, dict):
        built = {}
    return {
        "stream": built.get("stream") or {},
        "hooks": built.get("hooks") or {},
        "diagnostic": built.get("diagnostic") or {},
    }


async def cleanup_embedded_attempt_resources(
    params: Dict[str, Any],
) -> EmbeddedAttemptResourcesCleanup:
    """Cleanup the embedded-attempt resources.

    Mirrors :func:`cleanupEmbeddedAttemptResources`
    (``attempt.subscription-cleanup.ts``).
    """
    result: Any = await _maybe_await(
        _CLEANUP_EMBEDDED_ATTEMPT_RESOURCES(dict(params or {}))
    )
    if not isinstance(result, dict):
        result = {}
    return {
        "cleanedUp": bool(result.get("cleanedUp", True)),
        "unsubscribed": bool(result.get("unsubscribed", False)),
    }


async def _maybe_await(value: Any) -> Any:
    if hasattr(value, "__await__"):
        return await value
    return value


__all__ = [
    "EmbeddedAttemptResourcesCleanup",
    "EmbeddedSubscriptionParams",
    "build_embedded_subscription_params",
    "cleanup_embedded_attempt_resources",
    "set_build_embedded_subscription_params_hook",
    "set_cleanup_embedded_attempt_resources_hook",
]
