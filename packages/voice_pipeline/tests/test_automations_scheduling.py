"""packages/voice_pipeline/tests/test_automations_scheduling.py

Unit tests for schedule normalization (wall clock, relative, ISO, cron),
reminder ghost-chatter detection (OpenClaw parity), and CronRunner async firing.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
import re
from unittest.mock import AsyncMock

import pytest
from jarvis_cron_core import CronDecl, CronRunner
from jarvis_voice_pipeline.terminal_app import _detect_ghost_action_promise
from src.agents.sessions.tools.automations_tool import _normalize_schedule


def test_normalize_schedule_wall_clock_times() -> None:
    """Verify that wall-clock times like '17:10' and '5:10 PM' convert cleanly to ISO timestamps."""
    iso_1710 = _normalize_schedule("17:10")
    assert re.match(r"^\d{4}-\d{2}-\d{2}T17:10:00$", iso_1710)

    iso_510pm = _normalize_schedule("5:10 PM")
    assert re.match(r"^\d{4}-\d{2}-\d{2}T17:10:00$", iso_510pm)

    iso_510pm_compact = _normalize_schedule("5:10pm")
    assert re.match(r"^\d{4}-\d{2}-\d{2}T17:10:00$", iso_510pm_compact)

    iso_5pm = _normalize_schedule("5pm")
    assert re.match(r"^\d{4}-\d{2}-\d{2}T17:00:00$", iso_5pm)


def test_normalize_schedule_recurring_cron() -> None:
    """Verify that recurring=True produces a 5-field cron expression for wall clock times."""
    cron_expr = _normalize_schedule("17:10", recurring=True)
    assert cron_expr == "10 17 * * *"

    cron_expr_pm = _normalize_schedule("5:10 PM", recurring=True)
    assert cron_expr_pm == "10 17 * * *"


def test_normalize_schedule_durations_and_iso() -> None:
    """Verify durations, pure seconds, and space-separated timestamps."""
    iso_dur = _normalize_schedule("in 15m")
    assert "T" in iso_dur

    iso_sec = _normalize_schedule("300")
    assert "T" in iso_sec

    iso_raw = _normalize_schedule("2026-10-26 17:10:00")
    assert iso_raw == "2026-10-26T17:10:00"

    cron_raw = _normalize_schedule("*/5 * * * *")
    assert cron_raw == "*/5 * * * *"


def test_reminder_ghost_chatter_detection() -> None:
    """Verify that verbal reminder commitments without tool calls are detected as ghost-chatter."""
    goal = "5 baje 10 minetamaa Malai inpharm garnu."

    # Nepali verbal commitment
    speech_nepali = (
        "Hunchha sar, maile 5 bajer 10 minetamaa tapaaeenlaaee samjhaaunakaa laagi "
        "rimaaindar Set gardai chhu. ab Ma birsane chhaina."
    )
    assert _detect_ghost_action_promise(speech_nepali, goal) is True

    # Nepali verbal completion claim
    speech_completion = (
        "Hunchha sar, maile 4 bajer 24 minetamaa tapaaeenlaaee jaanakaaree dinako laagi "
        "rimaaindar Set garidie."
    )
    assert _detect_ghost_action_promise(speech_completion, goal) is True

    # English verbal commitment
    speech_en = "Sure Sir, I will schedule a reminder for you at 5:10 PM."
    assert _detect_ghost_action_promise(speech_en, goal) is True


def test_cron_runner_async_handler_execution() -> None:
    """Verify that CronRunner executes async coroutine handlers without hanging or error."""
    runner = CronRunner()
    fired_event = asyncio.Event()

    async def _async_job_handler() -> None:
        fired_event.set()

    job = CronDecl(
        id="test_async_job",
        schedule=datetime.now().replace(microsecond=0).isoformat(),
        handler=_async_job_handler,
    )
    runner.add(job)
    success = runner.run_job("test_async_job")
    assert success is True
    assert fired_event.is_set() is True


@pytest.mark.asyncio
async def test_automation_handler_notifies_live_engine() -> None:
    """Verify that when an automation handler fires, it delivers a notification to the active voice engine."""
    import builtins
    from src.agents.sessions.tools.automations_tool import _make_automation_handler

    received_notifications: list[str] = []

    class DummyEngine:
        def __init__(self) -> None:
            self.stop_event = asyncio.Event()

        def post_system_notification(self, text: str) -> None:
            received_notifications.append(text)

    dummy = DummyEngine()
    prev = getattr(builtins, "_JARVIS_ACTIVE_VOICE_ENGINE", None)
    builtins._JARVIS_ACTIVE_VOICE_ENGINE = dummy
    try:
        handler = _make_automation_handler("job_reminder_445", "4:45 PM भयो, जानकारी गराउनुहोस्।")
        await handler()

        assert len(received_notifications) == 1
        assert "job_reminder_445" in received_notifications[0]
        assert "4:45 PM भयो" in received_notifications[0]
    finally:
        builtins._JARVIS_ACTIVE_VOICE_ENGINE = prev


def test_cross_module_singleton_resolution() -> None:
    """Verify that NativeGeminiLiveEngine singleton is reachable across package/module boundaries."""
    from jarvis_voice_pipeline.terminal_app import NativeGeminiLiveEngine as E1
    from packages.voice_pipeline.src.jarvis_voice_pipeline.terminal_app import (
        NativeGeminiLiveEngine as E2,
    )

    class FakeState:
        pass

    state = FakeState()
    e1 = E1(state=state)  # type: ignore
    try:
        assert E1.get_active_engine() is e1
        # Cross-module access must resolve to the active instance
        assert E2.get_active_engine() is e1
    finally:
        E1._ACTIVE_VOICE_ENGINE = None
        E2._ACTIVE_VOICE_ENGINE = None
        import builtins

        if getattr(builtins, "_JARVIS_ACTIVE_VOICE_ENGINE", None) is e1:
            builtins._JARVIS_ACTIVE_VOICE_ENGINE = None


@pytest.mark.asyncio
async def test_desktop_action_get_time() -> None:
    """Verify that execute_desktop_action handles 'get_time' returning authoritative Nepal time."""
    import json
    from jarvis_desktop.desktop_actions import execute_desktop_action

    res_raw = await execute_desktop_action({"action": "get_time"})
    res = json.loads(res_raw)
    assert res["status"] == "success"
    assert "Asia/Kathmandu" in res["timezone"]
    assert "nepal_time" in res
    assert "iso_timestamp" in res
    assert "formatted" in res


def test_system_prompt_dynamic_time_directive() -> None:
    """Verify that build_jarvis_system_prompt instructs model to check computer(action='get_time')."""
    from pathlib import Path
    from jarvis_voice_pipeline.pipeline_builder import build_jarvis_system_prompt

    prompt = build_jarvis_system_prompt(Path("."), [])
    assert "computer(action='get_time')" in prompt
    assert "NEVER assume time is frozen" in prompt
    assert "youtube_play" in prompt


@pytest.mark.asyncio
async def test_send_audio_task_suppresses_mic_when_assistant_generating() -> None:
    """Verify that _send_audio_task never emits mic chunks to WebSocket while assistant is generating (preventing 1007 CONTENT_TYPE_AUDIO error)."""
    import threading
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    from jarvis_voice_pipeline import terminal_app

    engine = object.__new__(terminal_app.NativeGeminiLiveEngine)
    engine.stop_event = asyncio.Event()
    engine.audio_out_queue = asyncio.Queue()
    engine.audio_in_queue = asyncio.Queue()
    engine._speaking_lock = threading.Lock()
    engine._is_speaking = False
    engine._assistant_generating = True
    engine._turn_complete_received = False
    engine._tool_call_in_flight = False
    engine._pending_tool_response = False
    engine._tool_response_pending_turn = False
    engine._post_turn_silence_until = 0.0
    engine.state = SimpleNamespace(agent_state="THINKING")
    engine._ws_send_lock = asyncio.Lock()

    mock_session = SimpleNamespace(send_realtime_input=AsyncMock())
    engine.audio_out_queue.put_nowait(b"\x00" * 800)

    send_task = asyncio.create_task(engine._send_audio_task(mock_session))
    await asyncio.sleep(0.06)
    engine.stop_event.set()
    await send_task

    mock_session.send_realtime_input.assert_not_called()


@pytest.mark.asyncio
async def test_browser_open_youtube_search_url_auto_plays(monkeypatch) -> None:
    """Verify that opening a YouTube search query URL auto-delegates to youtube_play."""
    from extensions.browser.src.browser_tool import BrowserTool

    tool = BrowserTool()
    called_play: list[str] = []

    mock_runtime = AsyncMock()

    async def _mock_youtube_play(query: str, **kwargs):
        called_play.append(query)
        return {"ok": True, "action": "youtube_play", "query": query, "url": "https://www.youtube.com/watch?v=123"}

    mock_runtime.youtube_play = _mock_youtube_play
    mock_runtime.is_running = True
    monkeypatch.setattr("extensions.browser.src.browser_tool.get_browser_runtime", AsyncMock(return_value=mock_runtime))

    res = await tool.execute(
        "desktop_auto_control",
        {"action": "open", "url": "https://www.youtube.com/results?search_query=Arijit+Singh+song"},
    )
    assert len(called_play) == 1
    assert "Arijit Singh song" in called_play[0]
    assert res.details["action"] == "youtube_play"


@pytest.mark.asyncio
async def test_browser_google_search_on_youtube_delegates_to_youtube_play(monkeypatch) -> None:
    """Verify that calling google_search while active tab is YouTube delegates directly to youtube_play."""
    from types import SimpleNamespace
    from extensions.browser.src.browser_tool import BrowserTool

    tool = BrowserTool()
    called_play: list[str] = []

    mock_runtime = AsyncMock()

    async def _mock_youtube_play(query: str, **kwargs):
        called_play.append(query)
        return {"ok": True, "action": "youtube_play", "query": query}

    mock_runtime.youtube_play = _mock_youtube_play
    mock_runtime.get_page = AsyncMock(return_value=SimpleNamespace(url="https://www.youtube.com/results?search_query=test"))
    mock_runtime.is_running = True
    monkeypatch.setattr("extensions.browser.src.browser_tool.get_browser_runtime", AsyncMock(return_value=mock_runtime))

    res = await tool.execute(
        "desktop_auto_control",
        {"action": "google_search", "query": "Arijit Singh tere naam"},
    )
    assert len(called_play) == 1
    assert "Arijit Singh tere naam" in called_play[0]
    assert res.details["action"] == "youtube_play"


