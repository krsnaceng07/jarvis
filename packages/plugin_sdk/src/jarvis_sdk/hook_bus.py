"""jarvis_sdk.hook_bus — Plugin Hook Event Bus & Hook Catalog.

OpenClaw parity: mirrors
``openclaw-main/docs/plugins/plugin-hooks.md`` and
``openclaw-main/src/gateway/hooks.ts``.

Features:
- `HOOK_CATALOG`: Authoritative list of 34 plugin hook names.
- `HookRegistration`: Dataclass holding hook metadata (priority, matcher, timeout, triggers).
- `HookBus`: Priority-ordered event bus for plugin hook dispatch.
"""

from __future__ import annotations

import asyncio
import inspect
from dataclasses import dataclass, field
from typing import Any, Callable

HOOK_CATALOG: set[str] = {
    # Agent turn
    "before_model_resolve",
    "agent_turn_prepare",
    "before_prompt_build",
    "before_agent_run",
    "before_agent_reply",
    "before_agent_finalize",
    "agent_end",
    "heartbeat_prompt_contribution",
    # Conversation observation
    "model_call_started",
    "model_call_ended",
    "llm_input",
    "llm_output",
    # Tools
    "before_tool_call",
    "after_tool_call",
    "resolve_exec_env",
    "tool_result_persist",
    "before_message_write",
    # Messages & delivery
    "inbound_claim",
    "channel_pairing_requested",
    "message_received",
    "message_sending",
    "reply_payload_sending",
    "message_sent",
    "before_dispatch",
    "reply_dispatch",
    # Sessions & compaction
    "session_start",
    "session_end",
    "before_compaction",
    "after_compaction",
    "before_reset",
    # Subagents
    "subagent_spawned",
    "subagent_ended",
    "subagent_delivery_target",
    # Lifecycle
    "gateway_start",
    "gateway_stop",
    "cron_reconciled",
    "cron_changed",
    "before_install",
    "skill_proposal_evaluate",
    "skill_proposal_changed",
    "skill_changed",
}


@dataclass
class HookRegistration:
    hook_name: str
    handler: Callable[..., Any]
    plugin_id: str
    priority: int = 0
    registration_id: str | None = None
    timeout_ms: int = 15000
    eligible_triggers: list[str] = field(default_factory=list)
    matcher: list[str] = field(default_factory=list)


class HookBus:
    """Priority-ordered plugin event bus."""

    def __init__(self) -> None:
        self.registrations: list[HookRegistration] = []

    def on(
        self,
        hook_name: str,
        handler: Callable[..., Any],
        plugin_id: str = "core",
        priority: int = 0,
        registration_id: str | None = None,
        timeout_ms: int = 15000,
        eligible_triggers: list[str] | None = None,
        matcher: list[str] | None = None,
    ) -> HookRegistration:
        """Register a typed hook handler."""
        if hook_name not in HOOK_CATALOG:
            raise ValueError(f"Unknown plugin hook: '{hook_name}'")

        reg = HookRegistration(
            hook_name=hook_name,
            handler=handler,
            plugin_id=plugin_id,
            priority=priority,
            registration_id=registration_id,
            timeout_ms=timeout_ms,
            eligible_triggers=eligible_triggers or [],
            matcher=matcher or [],
        )
        self.registrations.append(reg)
        return reg

    def get_handlers(self, hook_name: str, tool_name: str | None = None) -> list[HookRegistration]:
        """Retrieve handlers sorted by priority (descending)."""
        matching = [r for r in self.registrations if r.hook_name == hook_name]
        if tool_name:
            matching = [r for r in matching if not r.matcher or tool_name in r.matcher]
        return sorted(matching, key=lambda r: r.priority, reverse=True)

    async def emit_pipeline(
        self, hook_name: str, event: dict[str, Any], context: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Dispatch a modifying pipeline hook in priority order."""
        handlers = self.get_handlers(hook_name, tool_name=event.get("toolName"))
        current_event = dict(event)
        ctx = context or {}

        for reg in handlers:
            try:
                if inspect.iscoroutinefunction(reg.handler):
                    res = await asyncio.wait_for(
                        reg.handler(current_event, ctx), timeout=reg.timeout_ms / 1000.0
                    )
                else:
                    res = reg.handler(current_event, ctx)

                if isinstance(res, dict):
                    if res.get("block") is True:
                        return res
                    if "params" in res:
                        current_event["params"] = res["params"]
            except Exception:
                pass

        return current_event


__all__ = [
    "HOOK_CATALOG",
    "HookBus",
    "HookRegistration",
]
