from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from src.hooks import HookBus
from src.tools.hook_async_dispatch import HookAwareAsyncToolDispatcher


@dataclass
class _MockReg:
    name: str
    handler: Any
    priority: int = 0
    timeout_ms: int | None = None


def test_hook_aware_async_dispatcher_fires_hooks_async_handler() -> None:
    bus = HookBus()
    called: list[Any] = []
    completed: list[Any] = []

    bus.register(_MockReg(name="tool_called", handler=lambda p: called.append(p)))

    async def _on_completed(payload: Any) -> None:
        await asyncio.sleep(0)
        completed.append(payload)

    bus.register(_MockReg(name="tool_completed", handler=_on_completed))

    async def ping(name: str, args: dict[str, Any]) -> str:
        await asyncio.sleep(0)
        return "pong"

    dispatcher = HookAwareAsyncToolDispatcher({"ping": ping}, bus)

    res = asyncio.run(dispatcher.execute("ping", {}, call_id="cid"))
    assert res.content in ("pong", '"pong"')
    assert len(called) == 1
    assert called[0]["tool"] == "ping"
    assert len(completed) == 1
    assert completed[0]["call_id"] == "cid"


def test_hook_aware_async_dispatcher_handles_sync_handler() -> None:
    bus = HookBus()
    called: list[Any] = []
    completed: list[Any] = []

    bus.register(_MockReg(name="tool_called", handler=lambda p: called.append(p)))
    bus.register(_MockReg(name="tool_completed", handler=lambda p: completed.append(p)))

    def ping_sync(name: str, args: dict[str, Any]) -> dict[str, str]:
        return {"ok": "yes"}

    dispatcher = HookAwareAsyncToolDispatcher({"ping_sync": ping_sync}, bus)
    res = asyncio.run(dispatcher.execute("ping_sync", {}, call_id="s1"))
    assert "ok" in res.content or "yes" in res.content
    assert len(called) == 1
    assert len(completed) == 1
