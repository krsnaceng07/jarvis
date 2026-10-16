"""Plugin registration hooks and descriptors for Voice Call."""

from __future__ import annotations

from typing import Any

from .plugin_helpers import execute_voice_call_action


async def handle_voice_call_tool(params: dict[str, Any], context: Any = None) -> dict[str, Any]:
    """Execute tool call from agent workspace."""
    action = params.get("action") or params.get("action_name") or "call"
    raw_config = getattr(context, "config", {}) if context else {}
    runtime = getattr(context, "voice_call_runtime", None) if context else None
    return await execute_voice_call_action(
        action_name=action,
        params=params,
        raw_config=raw_config,
        runtime=runtime,
    )


async def handle_voice_call_rpc(
    method: str, params: dict[str, Any], context: Any = None
) -> dict[str, Any]:
    """Execute gateway RPC method."""
    raw_config = getattr(context, "config", {}) if context else {}
    runtime = getattr(context, "voice_call_runtime", None) if context else None
    return await execute_voice_call_action(
        action_name=method,
        params=params,
        raw_config=raw_config,
        runtime=runtime,
    )
