"""jarvis.agents.embedded_agent_runner.stream_resolution — provider stream function resolution.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/stream-resolution.ts``.

Public surface:

- :func:`resolve_embedded_agent_base_stream_fn`
- :func:`describe_embedded_agent_stream_strategy`
- :func:`resolve_embedded_agent_api_key`
- :func:`resolve_embedded_agent_stream_fn`

Phase 7.6h-4 — focused minimal port.
"""
from __future__ import annotations

from typing import Any, Dict, Optional


# Installable hooks ---------------------------------------------------------

_resolve_embedded_agent_base_stream_fn_hook = None
_describe_embedded_agent_stream_strategy_hook = None
_resolve_embedded_agent_api_key_hook = None
_resolve_embedded_agent_stream_fn_hook = None


def set_resolve_embedded_agent_base_stream_fn_hook(fn) -> None:
    global _resolve_embedded_agent_base_stream_fn_hook
    _resolve_embedded_agent_base_stream_fn_hook = fn


def set_describe_embedded_agent_stream_strategy_hook(fn) -> None:
    global _describe_embedded_agent_stream_strategy_hook
    _describe_embedded_agent_stream_strategy_hook = fn


def set_resolve_embedded_agent_api_key_hook(fn) -> None:
    global _resolve_embedded_agent_api_key_hook
    _resolve_embedded_agent_api_key_hook = fn


def set_resolve_embedded_agent_stream_fn_hook(fn) -> None:
    global _resolve_embedded_agent_stream_fn_hook
    _resolve_embedded_agent_stream_fn_hook = fn


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def resolve_embedded_agent_base_stream_fn(params: Dict[str, Any]) -> Any:
    """Resolve the base stream function for an embedded agent session.

    Mirrors :func:`resolveEmbeddedAgentBaseStreamFn` (``stream-resolution.ts``).
    """
    if _resolve_embedded_agent_base_stream_fn_hook is not None:
        return _resolve_embedded_agent_base_stream_fn_hook(params)
    session = params.get("session") if isinstance(params.get("session"), dict) else {}
    agent = session.get("agent") if isinstance(session.get("agent"), dict) else {}
    base = agent.get("streamFn")
    if not base:
        raise RuntimeError("Agent session has no lifecycle-owned base stream.")
    return base


def describe_embedded_agent_stream_strategy(params: Dict[str, Any]) -> str:
    """Describe which stream strategy applies to the model.

    Mirrors :func:`describeEmbeddedAgentStreamStrategy` (``stream-resolution.ts``).
    """
    if _describe_embedded_agent_stream_strategy_hook is not None:
        v = _describe_embedded_agent_stream_strategy_hook(params)
        return v or "session-custom"
    if params.get("providerStreamFn"):
        return "provider"
    model = params.get("model") if isinstance(params.get("model"), dict) else {}
    provider = (model.get("provider") or "").lower()
    api = (model.get("api") or "").lower()
    if provider == "anthropic-vertex":
        return "anthropic-vertex"
    if provider == "openai" and api == "openai-chatgpt-responses":
        return "openclaw-native-codex-responses"
    if api == "anthropic-messages" and provider != "anthropic":
        return f"boundary-aware:{api or 'unknown'}"
    if (params.get("resolvedApiKey") or "").strip():
        return f"boundary-aware:{api or 'unknown'}"
    return "stream-simple"


async def resolve_embedded_agent_api_key(params: Dict[str, Any]) -> Optional[str]:
    """Resolve the runtime API key for the model.

    Mirrors :func:`resolveEmbeddedAgentApiKey` (``stream-resolution.ts``).
    """
    if _resolve_embedded_agent_api_key_hook is not None:
        v = _resolve_embedded_agent_api_key_hook(params)
        if hasattr(v, "__await__"):
            return await v  # type: ignore[func-returns-value]
        return v
    explicit = (params.get("resolvedApiKey") or "").strip()
    if explicit:
        return explicit
    storage = params.get("authStorage")
    if storage is not None and hasattr(storage, "getApiKey"):
        return await storage.getApiKey(params.get("provider", ""))
    return None


def resolve_embedded_agent_stream_fn(params: Dict[str, Any]) -> Any:
    """Resolve the stream function used for an embedded agent turn.

    Mirrors :func:`resolveEmbeddedAgentStreamFn` (``stream-resolution.ts``).
    """
    if _resolve_embedded_agent_stream_fn_hook is not None:
        return _resolve_embedded_agent_stream_fn_hook(params)
    # Focused port: return a stub that mirrors the contract; the runtime
    # delegates the heavy stream wiring to installable hooks.
    return params.get("providerStreamFn") or params.get("currentStreamFn")


__all__ = [
    "resolve_embedded_agent_base_stream_fn",
    "describe_embedded_agent_stream_strategy",
    "resolve_embedded_agent_api_key",
    "resolve_embedded_agent_stream_fn",
    "set_resolve_embedded_agent_base_stream_fn_hook",
    "set_describe_embedded_agent_stream_strategy_hook",
    "set_resolve_embedded_agent_api_key_hook",
    "set_resolve_embedded_agent_stream_fn_hook",
]
