"""Test Logbook observation reads bounding to at most 200 rows.

Ported from openclaw-main/extensions/logbook/src/observation-reads.test.ts.
"""

from __future__ import annotations

import os
import shutil
import tempfile
import time
from typing import Any
from unittest.mock import MagicMock
import pytest

from extensions.logbook.src.logbook_config import resolve_logbook_config
from extensions.logbook.src.prompts import build_ask_prompt
from extensions.logbook.src.service import LogbookService
from extensions.logbook.src.store import LogbookStore


@pytest.mark.asyncio
@pytest.mark.parametrize("count", [0, 199, 200, 201])
async def test_asks_with_latest_observations_reading_at_most_200(count: int) -> None:
    temp_dir = tempfile.mkdtemp(prefix="logbook-obs-reads-", dir="E:/jarvis/.tmp_pytest")
    data_dir = os.path.realpath(temp_dir)
    day = "2026-07-03"

    store = LogbookStore(data_dir)
    segments = [
        {
            "startMs": 1 + (i // 3) * 1000,
            "endMs": 1001 + (i // 3) * 1000,
            "text": f"Observation {i} 🦞",
        }
        for i in range(count)
    ]

    def seed_batch(batch_day: str) -> int:
        frame_id = store.insert_frame({
            "capturedAtMs": int(time.time() * 1000),
            "day": batch_day,
            "path": os.path.join(data_dir, "synthetic.jpg"),
            "screenIndex": 0,
            "byteSize": 0,
            "contentHash": f"synthetic-{batch_day}",
            "idle": False,
        })
        return store.create_batch({
            "day": batch_day,
            "startMs": 1,
            "endMs": 9223372036854775807,
            "frameIds": [frame_id],
        })

    batch_id = seed_batch(day)
    store.replace_observations(
        batch_id,
        day,
        [
            *segments,
            {"startMs": -10, "endMs": 0, "text": "Excluded end boundary"},
            {
                "startMs": 9223372036854775807,
                "endMs": 9223372036854775807,
                "text": "Excluded start boundary",
            },
        ],
    )
    # Different day observation (should be excluded)
    store.replace_observations(
        seed_batch("2026-07-04"),
        "2026-07-04",
        [{"startMs": 1, "endMs": 2, "text": "Excluded day"}],
    )
    store.close()

    mock_llm = MagicMock()

    async def mock_complete(args: dict[str, Any]) -> dict[str, Any]:
        return {
            "text": "Synthetic answer",
            "provider": "synthetic",
            "model": "synthetic",
        }

    mock_llm.complete = mock_complete

    class MockRuntime:
        def __init__(self) -> None:
            self.llm = mock_llm

    runtime = MockRuntime()
    service = LogbookService(
        resolve_logbook_config({"captureEnabled": False}),
        deps={
            "dataDir": data_dir,
            "runtime": runtime,
            "fullConfig": {},
        },
    )
    service.start()

    try:
        answer = await service.ask(day, "What happened?")
        assert answer == "Synthetic answer"

        # Verify the observations read in range are at most 200
        reopened = LogbookStore(data_dir)
        obs_read = reopened.observations_in_range(day, 0, 9223372036854775807, 200)
        reopened.close()

        expected_count = min(count, 200)
        assert len(obs_read) == expected_count
        if count > 0:
            # Most recent observations should be returned
            assert obs_read[-1]["text"] == f"Observation {count - 1} 🦞"
    finally:
        await service.stop()
        shutil.rmtree(temp_dir, ignore_errors=True)
