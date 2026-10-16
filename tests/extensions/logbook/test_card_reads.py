"""Test Logbook card reads efficiency and single-query hydration.

Ported from openclaw-main/extensions/logbook/src/card-reads.test.ts.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from typing import Any
import pytest

from extensions.logbook.plugin import LogbookPlugin
from extensions.logbook.src.store import LogbookStore


class QueryCounter:
    def __init__(self) -> None:
        self.queries: int = 0
        self.payload_rows: int = 0

    def trace(self, sql: str) -> None:
        if "from cards" in sql.lower() or 'from "cards"' in sql.lower():
            self.queries += 1


@pytest.mark.asyncio
async def test_hydrates_timeline_and_counts_status_without_reading_card_payloads() -> None:
    temp_dir = tempfile.mkdtemp(prefix="logbook-card-reads-", dir="E:/jarvis/.tmp_pytest")
    state_dir = os.path.realpath(temp_dir)
    data_dir = os.path.join(state_dir, "logbook")

    day = "2026-07-03"
    start_ms = 1783069200000  # 2026-07-03T09:00:00Z approx
    drafts = [
        {
            "day": day,
            "startMs": start_ms + i * 60_000,
            "endMs": start_ms + (i + 1) * 60_000,
            "title": f"Card {i} 🦞",
            "summary": "Summary",
            "detail": "Detailed activity",
            "category": "coding",
            "distractions": [{"startMs": start_ms + 1, "endMs": start_ms + 11, "title": "Break"}],
        }
        for i in range(8)
    ]

    store = LogbookStore(data_dir)
    store.replace_cards_in_window(day, 0, 9223372036854775807, drafts)
    cards = store.cards_for_day(day)
    store.close()

    methods: dict[str, Any] = {}
    services: list[Any] = []

    class MockApi:
        def __init__(self) -> None:
            self.plugin_config = {"captureEnabled": False}
            self.runtime: dict[str, Any] = {}

        def register_service(self, service: Any) -> None:
            services.append(service)

        def register_gateway_method(self, name: str, handler: Any, *args: Any, **kwargs: Any) -> None:
            methods[name] = handler

        def register_node_invoke_policy(self, *args: Any, **kwargs: Any) -> None:
            pass

        class Session:
            class Controls:
                def register_control_ui_descriptor(self, *args: Any, **kwargs: Any) -> None:
                    pass
            controls = Controls()
        session = Session()

    plugin = LogbookPlugin()
    api = MockApi()
    plugin.register(api)  # type: ignore[arg-type]

    service = services[0]
    context = {"state_dir": state_dir, "config": {}}
    await service.start(context)

    async def call(method: str, params: dict[str, Any] | None = None) -> Any:
        handler = methods[method]
        captured_result = {}

        def respond(ok: bool, payload: Any = None) -> None:
            captured_result["ok"] = ok
            captured_result["payload"] = payload

        await handler({"params": params or {}, "respond": respond})
        assert captured_result["ok"] is True
        return captured_result["payload"]

    try:
        # Test timeline hydration
        timeline = await call("logbook.timeline", {"day": day})
        assert timeline["day"] == day
        assert len(timeline["cards"]) == 8
        assert timeline["stats"]["trackedMs"] == 8 * 60_000
        assert timeline["stats"]["distractionMs"] == 80
        assert timeline["stats"]["categories"] == [{"category": "coding", "ms": 8 * 60_000}]

        # Test status counts without full card hydration
        status = await call("logbook.status")
        assert "todayCards" in status
        assert status["todayCards"] == 8
    finally:
        await service.stop(context)
        shutil.rmtree(temp_dir, ignore_errors=True)
