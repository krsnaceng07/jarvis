"""jarvis.infra.heartbeat_wake — Heartbeat wake dispatch and request tracking.

OpenClaw parity: mirrors ``openclaw-main/src/infra/heartbeat-wake.ts``.
Provides reactive wake requests when background tasks, exec processes, or external
events complete, triggering immediate evaluation in the agent session loop.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger("jarvis.infra.heartbeat_wake")

HeartbeatWakeHandler = Callable[[Dict[str, Any]], Any]

_handler: Optional[HeartbeatWakeHandler] = None
_loop: Optional[asyncio.AbstractEventLoop] = None
_heartbeats_enabled: bool = True


def set_heartbeats_enabled(enabled: bool) -> None:
    global _heartbeats_enabled
    _heartbeats_enabled = enabled


def are_heartbeats_enabled() -> bool:
    return _heartbeats_enabled


def set_heartbeat_wake_handler(handler: Optional[HeartbeatWakeHandler]) -> Callable[[], None]:
    """Register (or clear) the heartbeat wake handler.

    Returns a disposer callable to unregister the handler.
    """
    global _handler, _loop
    _handler = handler
    try:
        _loop = asyncio.get_running_loop()
    except RuntimeError:
        pass

    def dispose() -> None:
        global _handler
        if _handler is handler:
            _handler = None

    return dispose


def get_heartbeat_wake_handler() -> Optional[HeartbeatWakeHandler]:
    return _handler


def request_heartbeat(opts: Dict[str, Any]) -> None:
    """Request an immediate or deferred heartbeat wake for an agent/session.

    Mirrors ``requestHeartbeat`` in OpenClaw.
    ``opts`` typically includes:
      - ``source``: "background-task" | "exec-event" | "cron" | etc.
      - ``intent``: "immediate" | "event" | "scheduled"
      - ``sessionKey``: target session key
      - ``reason``: diagnostic string
      - ``agentId``: optional agent id
    """
    if not _heartbeats_enabled:
        return

    logger.info(
        "request_heartbeat: source=%s intent=%s sessionKey=%s reason=%s",
        opts.get("source"),
        opts.get("intent"),
        opts.get("sessionKey"),
        opts.get("reason"),
    )

    # 1. Notify session_state_notices hook if registered
    try:
        from src.sessions.session_state_notices import _request_heartbeat
        _request_heartbeat(opts)
    except Exception as exc:
        logger.debug("session_state_notices _request_heartbeat error: %s", exc)

    # 2. Dispatch to registered handler
    handler = _handler
    if handler is None:
        return

    try:
        # Check if running in async loop
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = _loop

        if asyncio.iscoroutinefunction(handler):
            if current_loop and current_loop.is_running():
                current_loop.call_soon_threadsafe(
                    lambda: asyncio.create_task(handler(opts))
                )
            else:
                asyncio.run(handler(opts))
        else:
            if current_loop and current_loop.is_running():
                current_loop.call_soon_threadsafe(handler, opts)
            else:
                handler(opts)
    except Exception as exc:
        logger.warning("Error dispatching heartbeat wake: %s", exc)


def reset_heartbeat_wake_for_tests() -> None:
    global _handler, _loop, _heartbeats_enabled
    _handler = None
    _loop = None
    _heartbeats_enabled = True


__all__ = [
    "are_heartbeats_enabled",
    "get_heartbeat_wake_handler",
    "request_heartbeat",
    "reset_heartbeat_wake_for_tests",
    "set_heartbeat_wake_handler",
    "set_heartbeats_enabled",
]
