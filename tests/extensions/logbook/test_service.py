"""Unit tests for LogbookService.

Mirrors OpenClaw's ``extensions/logbook/src/service.test.ts`` 1:1.
"""

from __future__ import annotations

import base64
import os
from pathlib import Path
import pytest

from extensions.logbook.src.logbook_config import resolve_logbook_config
from extensions.logbook.src.service import LogbookService


class QuietLogger:
    def info(self, *args, **kwargs): pass
    def warn(self, *args, **kwargs): pass
    def error(self, *args, **kwargs): pass
    def debug(self, *args, **kwargs): pass


class MockRuntime:
    def __init__(self, nodes: list[dict], invoke_fn: Any) -> None:
        self.nodes = MockNodes(nodes, invoke_fn)


class MockNodes:
    def __init__(self, nodes: list[dict], invoke_fn: Any) -> None:
        self._nodes = nodes
        self._invoke_fn = invoke_fn
        self.invoked: list[dict] = []

    async def list(self, *args, **kwargs):
        return {"nodes": self._nodes}

    async def invoke(self, args: dict):
        self.invoked.append({"nodeId": args["nodeId"], "command": args["command"]})
        return await self._invoke_fn(args)


FRAME_PAYLOAD = {
    "payload": {"format": "jpeg", "base64": base64.b64encode(b"fake-jpeg").decode("ascii")},
}


def make_service(
    tmp_path: Path,
    nodes: list[dict],
    invoke_fn: Any,
    config: dict | None = None,
    full_config: dict | None = None,
):
    data_dir = str(tmp_path)
    runtime = MockRuntime(nodes, invoke_fn)
    service = LogbookService(
        config=resolve_logbook_config({"captureEnabled": True, **(config or {})}),
        deps={
            "runtime": runtime,
            "fullConfig": full_config or {},
            "logger": QuietLogger(),
            "dataDir": data_dir,
        },
    )
    service.start()
    return service, runtime


@pytest.mark.asyncio
async def test_prefers_app_nodes_over_headless_node_hosts(tmp_path: Path) -> None:
    async def invoke_fn(args):
        return FRAME_PAYLOAD

    service, runtime = make_service(
        tmp_path,
        nodes=[
            {"nodeId": "a-headless", "commands": ["logbook.snapshot"]},
            {"nodeId": "b-mac-app", "commands": ["screen.snapshot"]},
        ],
        invoke_fn=invoke_fn,
    )
    try:
        await service.capture_tick()
        assert runtime.nodes.invoked == [{"nodeId": "b-mac-app", "command": "screen.snapshot"}]
        status = service.status()
        assert status["pendingFrames"] == 1
        assert status["lastCaptureError"] is None
    finally:
        await service.stop()


@pytest.mark.asyncio
async def test_rotates_to_next_capture_node_after_failure(tmp_path: Path) -> None:
    async def invoke_fn(args):
        if args["nodeId"] == "a-broken":
            return {"payload": {"error": "logbook.snapshot is not supported on linux"}}
        return FRAME_PAYLOAD

    service, runtime = make_service(
        tmp_path,
        nodes=[
            {"nodeId": "a-broken", "commands": ["logbook.snapshot"]},
            {"nodeId": "b-working", "commands": ["logbook.snapshot"]},
        ],
        invoke_fn=invoke_fn,
    )
    try:
        await service.capture_tick()
        await service.capture_tick()
        assert [call["nodeId"] for call in runtime.nodes.invoked] == ["a-broken", "b-working"]
        assert service.status()["lastCaptureError"] is None
    finally:
        await service.stop()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "base64_val",
    [
        "not-base64!",
        {"encoded": "ZmFrZQ=="},
        ["ZmFrZQ=="],
    ],
)
async def test_rejects_invalid_snapshot_payload(tmp_path: Path, base64_val: Any) -> None:
    async def invoke_fn(args):
        return {"payload": {"format": "jpeg", "base64": base64_val}}

    service, runtime = make_service(
        tmp_path,
        nodes=[{"nodeId": "capture-node", "commands": ["logbook.snapshot"]}],
        invoke_fn=invoke_fn,
    )
    try:
        await service.capture_tick()
        status = service.status()
        assert status["pendingFrames"] == 0
        assert "invalid image payload" in (status["lastCaptureError"] or "")
    finally:
        await service.stop()


@pytest.mark.asyncio
async def test_borrows_only_media_provider_with_structured_extraction(tmp_path: Path) -> None:
    async def invoke_fn(args):
        return FRAME_PAYLOAD

    service, runtime = make_service(
        tmp_path,
        nodes=[],
        invoke_fn=invoke_fn,
        full_config={
            "tools": {
                "media": {
                    "models": [
                        {"provider": "openai", "model": "gpt-5.5", "capabilities": ["image"]},
                        {"provider": " Codex ", "model": "gpt-5.5", "capabilities": ["image"]},
                    ]
                }
            }
        },
    )
    try:
        status = service.status()
        assert status["visionModel"] == "codex/gpt-5.5"
        assert status["visionModelSource"] == "media-defaults"
    finally:
        await service.stop()


@pytest.mark.asyncio
async def test_reports_missing_model_when_defaults_cannot_extract(tmp_path: Path) -> None:
    async def invoke_fn(args):
        return FRAME_PAYLOAD

    service, runtime = make_service(
        tmp_path,
        nodes=[],
        invoke_fn=invoke_fn,
        full_config={
            "tools": {
                "media": {
                    "models": [{"provider": "openai", "model": "gpt-5.5", "capabilities": ["image"]}]
                }
            }
        },
    )
    try:
        status = service.status()
        assert status["visionModel"] is None
        assert status["visionModelSource"] == "missing"
    finally:
        await service.stop()


@pytest.mark.asyncio
async def test_returns_capture_host_timezone_without_exposing_data_dir(tmp_path: Path) -> None:
    async def invoke_fn(args):
        return FRAME_PAYLOAD

    service, runtime = make_service(
        tmp_path,
        nodes=[],
        invoke_fn=invoke_fn,
    )
    try:
        status = service.status()
        assert "timeZone" in status
        assert "dataDir" not in status
    finally:
        await service.stop()
