"""jarvis.agents.embedded_agent_runner.extensions — extension factories for embedded-agent runtime.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/extensions.ts``.

Public surface:

- :func:`build_embedded_extension_factories`

Phase 7.6h-3 — focused minimal port.
"""
from __future__ import annotations

import uuid
from typing import Any, Callable, Dict, List, Optional


_build_embedded_extension_factories_hook = None


def set_build_embedded_extension_factories_hook(fn) -> None:
    global _build_embedded_extension_factories_hook
    _build_embedded_extension_factories_hook = fn


def _record_from_unknown(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _snapshot_tool_send_receipt(details: Any) -> Any:
    record = _record_from_unknown(details)
    tool_send = record.get("toolSend")
    if tool_send and isinstance(tool_send, dict):
        return dict(tool_send)
    return tool_send


def _build_agent_tool_result_middleware_factory(
    session_manager: Any,
    run_id: Optional[str] = None,
) -> Callable:
    def _factory(agent: Any) -> Callable:
        async def _on_tool_result(raw_event: Any, ctx: Dict[str, Any]) -> Any:
            event = _record_from_unknown(raw_event)
            tool_name = event.get("toolName")
            if not tool_name:
                return None
            event_tool_call_id = event.get("toolCallId")
            if not isinstance(event_tool_call_id, str) or not event_tool_call_id.strip():
                event_tool_call_id = None
            tool_call_id = event_tool_call_id or f"jarvis-{uuid.uuid4()}"
            content = event.get("content") if isinstance(event.get("content"), list) else []
            current = {"content": content, "details": event.get("details")}
            raw_tool_send = _snapshot_tool_send_receipt(current["details"])
            if event_tool_call_id and raw_tool_send is not None:
                # Routing evidence stays private so middleware may fully replace
                # result details.
                try:
                    session_manager.record_tool_send_receipt(  # type: ignore[attr-defined]
                        event_tool_call_id, raw_tool_send
                    )
                except Exception:
                    pass
            return {
                "content": current["content"],
                "details": current["details"],
            }
        try:
            agent.on("tool_result", _on_tool_result)
        except Exception:
            pass
        return _factory
    return _factory


def build_embedded_extension_factories(params: Dict[str, Any]) -> List[Callable]:
    """Build extension factories available to embedded-agent runtime sessions.

    Mirrors :func:`buildEmbeddedExtensionFactories` (``extensions.ts``).
    """
    if _build_embedded_extension_factories_hook is not None:
        return _build_embedded_extension_factories_hook(params) or []
    factories: List[Callable] = []
    session_manager = params.get("sessionManager")
    run_id = params.get("runId")
    factories.append(_build_agent_tool_result_middleware_factory(session_manager, run_id))
    return factories


__all__ = [
    "build_embedded_extension_factories",
    "set_build_embedded_extension_factories_hook",
]
