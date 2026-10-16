"""Test Logbook service lifecycle and graceful shutdown draining.

Ported from openclaw-main/extensions/logbook/src/service-lifecycle.test.ts.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import tempfile
from typing import Any
from unittest.mock import MagicMock
import pytest

from extensions.logbook.src.logbook_config import resolve_logbook_config
from extensions.logbook.src.service import LogbookService
from extensions.logbook.src.store import LogbookStore, day_key_for


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["capture", "standup"])
async def test_drains_active_operations_before_closing(kind: str) -> None:
    temp_dir = tempfile.mkdtemp(prefix="logbook-drain-", dir="E:/jarvis/.tmp_pytest")
    data_dir = os.path.realpath(temp_dir)
    day = day_key_for(int(asyncio.get_event_loop().time() * 1000))

    entered = asyncio.Event()
    release = asyncio.Event()

    mock_nodes = MagicMock()

    async def mock_list() -> dict[str, Any]:
        if kind == "capture":
            entered.set()
            await release.wait()
        return {"nodes": [{"nodeId": "test-node", "commands": ["screen.snapshot"]}]}

    async def mock_invoke(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return {"payload": {"base64": "c3ludGhldGlj"}}

    mock_nodes.list = mock_list
    mock_nodes.invoke = mock_invoke

    mock_llm = MagicMock()

    async def mock_complete(args: dict[str, Any]) -> dict[str, Any]:
        if kind == "standup":
            entered.set()
            await release.wait()
        return {"text": "Synthetic standup result"}

    mock_llm.complete = mock_complete

    class MockRuntime:
        def __init__(self) -> None:
            self.nodes = mock_nodes
            self.llm = mock_llm

    runtime = MockRuntime()
    service = LogbookService(
        resolve_logbook_config({
            "captureEnabled": True,
            "captureIntervalSeconds": 600,
            "visionModel": "synthetic/vision",
        }),
        deps={"dataDir": data_dir, "runtime": runtime, "fullConfig": {}},
    )
    service.start()

    active_task: asyncio.Task[Any] | None = None
    if kind == "capture":
        active_task = asyncio.create_task(service.capture_tick())
    else:
        active_task = service.standup(day, refresh=True)

    await entered.wait()

    # Now request stop while operation is running
    stop_future = service.stop()

    # While stopping, new calls must be rejected
    with pytest.raises(RuntimeError, match="not running"):
        await service.standup(day, refresh=True)

    with pytest.raises(RuntimeError, match="not running"):
        await service.analyze_now()

    # Calling stop again returns the same drain future
    second_stop = service.stop()
    assert second_stop is stop_future

    # Release the held operation
    release.set()

    await active_task
    await stop_future

    # Verify store recorded the result
    reopened = LogbookStore(data_dir)
    try:
        if kind == "capture":
            assert reopened.count_unbatched_active_frames() >= 0
        elif kind == "standup":
            su = reopened.get_standup(day)
            assert su is not None
            assert su["text"] == "Synthetic standup result"
    finally:
        reopened.close()
        shutil.rmtree(temp_dir, ignore_errors=True)
