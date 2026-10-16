"""tests.test_youtube_provider_and_tools — Comprehensive test suite for YouTubeProvider and tools.

OpenClaw parity:
- Validates provider abstraction layer, tab affinity preservation, and HTML5 video verification.
- Validates 7 granular tools, parameter schemas, error boundaries, and dispatch mapping.
- Validates desktop live pipeline registration and execution verification.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from jarvis_sdk import Ok
from src.application_automation.active_tab_tracker import ActiveTabTracker
from src.application_automation.application_session_manager import ApplicationSessionManager
from src.application_automation.providers.youtube_provider import YouTubeProvider
from src.application_automation.tools.youtube_tools import (
    YOUTUBE_TOOL_DECLARATIONS,
    dispatch_youtube_tool,
    set_youtube_provider,
    youtube_get_state_tool,
    youtube_pause_tool,
    youtube_play_tool,
    youtube_resume_tool,
    youtube_search_tool,
    youtube_set_volume_tool,
    youtube_skip_ad_tool,
    youtube_subscribe_tool,
    youtube_unsubscribe_tool,
    youtube_close_tool,
)


class MockPage:
    """Mock Playwright Page for provider testing."""

    def __init__(self, url: str = "https://www.youtube.com", is_closed: bool = False):
        self.url = url
        self._is_closed = is_closed
        self.bring_to_front = AsyncMock()
        self.evaluate = AsyncMock(return_value={"paused": False, "currentTime": 10.0, "duration": 180.0, "volume": 50, "muted": False})
        self.title = AsyncMock(return_value="YouTube Test Video")

    def is_closed(self) -> bool:
        return self._is_closed


class MockBrowserRuntime:
    """Mock BrowserRuntime managing pages and tabs."""

    def __init__(self):
        self.opened_tabs: list[dict[str, Any]] = []
        self.pages: dict[str, MockPage] = {}
        self.default_page = MockPage()

    async def get_page(self, target_id: str | None = None) -> Any:
        if target_id and target_id in self.pages:
            return self.pages[target_id]
        return self.default_page

    async def open_tab(self, url: str = "", label: str = "", **kwargs: Any) -> dict[str, Any]:
        tid = f"tab_{len(self.opened_tabs) + 1}"
        record = {"targetId": tid, "url": url, "label": label}
        self.opened_tabs.append(record)
        self.pages[tid] = MockPage(url=url)
        return record


# ── Provider Tests ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_provider_tab_affinity_reuses_existing_tab():
    """Verify that YouTubeProvider reuses existing YouTube tab without opening new ones."""
    tracker = ActiveTabTracker()
    tracker.register_tab(target_id="tab_yt_1", url="https://www.youtube.com/watch?v=123", label="youtube", app_type="youtube")

    mock_runtime = MockBrowserRuntime()
    existing_page = MockPage(url="https://www.youtube.com/watch?v=123")
    mock_runtime.pages["tab_yt_1"] = existing_page

    provider = YouTubeProvider(tab_tracker=tracker, browser_runtime=mock_runtime)
    page = await provider.ensure_active_page()

    assert page == existing_page
    assert len(mock_runtime.opened_tabs) == 0
    existing_page.bring_to_front.assert_awaited_once()


@pytest.mark.asyncio
async def test_provider_tab_affinity_opens_new_tab_if_none_active():
    """Verify that YouTubeProvider opens a new tab when no YouTube tab is open."""
    tracker = ActiveTabTracker()
    mock_runtime = MockBrowserRuntime()

    provider = YouTubeProvider(tab_tracker=tracker, browser_runtime=mock_runtime)
    page = await provider.ensure_active_page()

    assert page is not None
    assert len(mock_runtime.opened_tabs) == 1
    assert mock_runtime.opened_tabs[0]["label"] == "youtube"


@pytest.mark.asyncio
async def test_provider_play_with_query():
    """Verify play() with query initiates search_and_play and syncs runtime."""
    mock_session = MagicMock(spec=ApplicationSessionManager)
    mock_session.get_adapter.return_value = None
    mock_session.execute_action = AsyncMock(
        return_value=Ok({
            "action": "search_and_play",
            "video_title": "Lo-Fi Beats to Relax",
            "verification": {"effect": "confirmed", "verified": True},
        })
    )

    provider = YouTubeProvider(session_manager=mock_session)
    mock_page = MockPage()

    res = await provider.play(query="lofi beats", page_override=mock_page)

    assert res.is_ok
    payload = res.unwrap()
    assert payload["video_title"] == "Lo-Fi Beats to Relax"
    mock_session.execute_action.assert_awaited_once_with(
        "youtube", "search_and_play", {"query": "lofi beats"}, mock_page
    )


@pytest.mark.asyncio
async def test_provider_pause_and_resume():
    """Verify pause and resume operations through the provider."""
    mock_session = MagicMock(spec=ApplicationSessionManager)
    mock_session.get_adapter.return_value = None
    mock_session.execute_action = AsyncMock(
        side_effect=[
            Ok({"action": "pause", "paused": True, "verification": {"verified": True}}),
            Ok({"action": "resume", "paused": False, "verification": {"verified": True}}),
        ]
    )

    provider = YouTubeProvider(session_manager=mock_session)
    mock_page = MockPage()

    pause_res = await provider.pause(page_override=mock_page)
    assert pause_res.is_ok
    assert pause_res.unwrap()["paused"] is True

    resume_res = await provider.resume(page_override=mock_page)
    assert resume_res.is_ok
    assert resume_res.unwrap()["paused"] is False


@pytest.mark.asyncio
async def test_provider_search_validation():
    """Verify search requires non-empty query string."""
    provider = YouTubeProvider()
    res = await provider.search("   ")
    assert not res.is_ok
    assert res.error == "Search query cannot be empty"


@pytest.mark.asyncio
async def test_provider_volume_clamping():
    """Verify set_volume clamps values to 0-100 range."""
    mock_session = MagicMock(spec=ApplicationSessionManager)
    mock_session.get_adapter.return_value = None
    mock_session.execute_action = AsyncMock(return_value=Ok({"action": "set_volume", "volume": 100}))

    provider = YouTubeProvider(session_manager=mock_session)
    mock_page = MockPage()

    res = await provider.set_volume(150, page_override=mock_page)
    assert res.is_ok
    mock_session.execute_action.assert_awaited_once_with(
        "youtube", "set_volume", {"volume": 100}, mock_page
    )


# ── Granular Tools Tests ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_youtube_play_tool():
    """Verify youtube_play_tool formatting."""
    mock_provider = MagicMock(spec=YouTubeProvider)
    mock_provider.play = AsyncMock(
        return_value=Ok({
            "video_title": "Interstellar Theme",
            "verification": {"verified": True},
        })
    )
    set_youtube_provider(mock_provider)

    try:
        out = await youtube_play_tool({"query": "interstellar"})
        assert "SUCCESS: Playing 'Interstellar Theme' on YouTube." in out
        assert "[Playback Verified via HTML5 <video>]" in out
    finally:
        set_youtube_provider(None)


@pytest.mark.asyncio
async def test_youtube_pause_tool():
    """Verify youtube_pause_tool formatting."""
    mock_provider = MagicMock(spec=YouTubeProvider)
    mock_provider.pause = AsyncMock(
        return_value=Ok({"action": "pause", "verification": {"verified": True}})
    )
    set_youtube_provider(mock_provider)

    try:
        out = await youtube_pause_tool({})
        assert "SUCCESS: Paused YouTube video playback." in out
        assert "[Pause Verified via HTML5 <video>]" in out
    finally:
        set_youtube_provider(None)


@pytest.mark.asyncio
async def test_youtube_resume_tool():
    """Verify youtube_resume_tool formatting."""
    mock_provider = MagicMock(spec=YouTubeProvider)
    mock_provider.resume = AsyncMock(
        return_value=Ok({"action": "resume", "verification": {"verified": True}})
    )
    set_youtube_provider(mock_provider)

    try:
        out = await youtube_resume_tool({})
        assert "SUCCESS: Resumed YouTube video playback." in out
        assert "[Playback Verified via HTML5 <video>]" in out
    finally:
        set_youtube_provider(None)


@pytest.mark.asyncio
async def test_youtube_search_tool():
    """Verify youtube_search_tool requires query."""
    mock_provider = MagicMock(spec=YouTubeProvider)
    mock_provider.search = AsyncMock(return_value=Ok({"action": "search", "query": "python tutorial"}))
    set_youtube_provider(mock_provider)

    try:
        err_out = await youtube_search_tool({"query": ""})
        assert "ERROR: 'query' parameter is required" in err_out

        ok_out = await youtube_search_tool({"query": "python tutorial"})
        assert "SUCCESS: Searched YouTube for 'python tutorial'." in ok_out
    finally:
        set_youtube_provider(None)


@pytest.mark.asyncio
async def test_youtube_skip_ad_tool():
    """Verify youtube_skip_ad_tool formatting."""
    mock_provider = MagicMock(spec=YouTubeProvider)
    mock_provider.skip_ad = AsyncMock(return_value=Ok({"skipped": True}))
    set_youtube_provider(mock_provider)

    try:
        out = await youtube_skip_ad_tool({})
        assert "SUCCESS: Skipped YouTube advertisement." in out
    finally:
        set_youtube_provider(None)


@pytest.mark.asyncio
async def test_youtube_set_volume_tool():
    """Verify youtube_set_volume_tool validation."""
    mock_provider = MagicMock(spec=YouTubeProvider)
    mock_provider.set_volume = AsyncMock(return_value=Ok({"action": "set_volume", "volume": 75}))
    set_youtube_provider(mock_provider)

    try:
        err_missing = await youtube_set_volume_tool({})
        assert "ERROR: 'volume' parameter (0-100) is required." in err_missing

        err_invalid = await youtube_set_volume_tool({"volume": "loud"})
        assert "ERROR: Invalid volume value: 'loud'." in err_invalid

        ok_out = await youtube_set_volume_tool({"volume": 75})
        assert "SUCCESS: YouTube volume set to 75%." in ok_out
    finally:
        set_youtube_provider(None)


@pytest.mark.asyncio
async def test_youtube_get_state_tool():
    """Verify youtube_get_state_tool formatting."""
    mock_provider = MagicMock(spec=YouTubeProvider)
    mock_provider.get_state = AsyncMock(
        return_value=Ok({
            "found": True,
            "title": "Quantum Physics Explained",
            "paused": False,
            "currentTime": 45.2,
            "duration": 600.0,
            "volume": 80,
            "muted": False,
            "ad_active": False,
        })
    )
    set_youtube_provider(mock_provider)

    try:
        out = await youtube_get_state_tool({})
        assert "YouTube State: Status=Playing" in out
        assert "Title='Quantum Physics Explained'" in out
        assert "Time=45.2s/600.0s" in out
        assert "Volume=80%" in out
    finally:
        set_youtube_provider(None)


@pytest.mark.asyncio
async def test_dispatch_youtube_tool():
    """Verify dispatch_youtube_tool routes to the correct tool function."""
    mock_provider = MagicMock(spec=YouTubeProvider)
    mock_provider.pause = AsyncMock(return_value=Ok({"action": "pause", "verification": {"verified": True}}))
    set_youtube_provider(mock_provider)

    try:
        out = await dispatch_youtube_tool("youtube_pause", {})
        assert "SUCCESS: Paused YouTube video playback." in out

        unknown = await dispatch_youtube_tool("youtube_unknown", {})
        assert "ERROR: Unknown YouTube tool 'youtube_unknown'." in unknown
    finally:
        set_youtube_provider(None)


@pytest.mark.asyncio
async def test_youtube_subscribe_tool():
    """Verify youtube_subscribe_tool handles new subscription and already subscribed states."""
    mock_provider = MagicMock(spec=YouTubeProvider)
    mock_provider.subscribe = AsyncMock(return_value=Ok({"action": "subscribe", "already_subscribed": False, "clicked": True}))
    set_youtube_provider(mock_provider)

    try:
        out = await youtube_subscribe_tool({})
        assert "SUCCESS: Subscribed to channel. [Subscription Verified]" in out

        # Test already subscribed
        mock_provider.subscribe = AsyncMock(return_value=Ok({"action": "subscribe", "already_subscribed": True, "button_text": "Subscribed"}))
        out_already = await youtube_subscribe_tool({})
        assert "SUCCESS: Already subscribed to this channel ('Subscribed'). [Precondition Satisfied]" in out_already
    finally:
        set_youtube_provider(None)


@pytest.mark.asyncio
async def test_youtube_unsubscribe_tool():
    """Verify youtube_unsubscribe_tool handles multi-tier confirmation and already unsubscribed."""
    mock_provider = MagicMock(spec=YouTubeProvider)
    mock_provider.unsubscribe = AsyncMock(return_value=Ok({"action": "unsubscribe", "verified": True, "already_unsubscribed": False}))
    set_youtube_provider(mock_provider)

    try:
        out = await youtube_unsubscribe_tool({})
        assert "SUCCESS: Unsubscribed from channel. [Unsubscribe Confirmed & Verified]" in out

        # Test already unsubscribed
        mock_provider.unsubscribe = AsyncMock(return_value=Ok({"action": "unsubscribe", "already_unsubscribed": True}))
        out_already = await youtube_unsubscribe_tool({})
        assert "SUCCESS: Already unsubscribed from this channel. [Precondition Satisfied]" in out_already
    finally:
        set_youtube_provider(None)


@pytest.mark.asyncio
async def test_provider_subscribe_and_unsubscribe_delegation():
    """Verify YouTubeProvider.subscribe and unsubscribe execute actions via session manager."""
    mock_mgr = MagicMock(spec=ApplicationSessionManager)
    mock_mgr.execute_action = AsyncMock(return_value=Ok({"action": "subscribe", "verified": True}))

    mock_runtime = MockBrowserRuntime()
    provider = YouTubeProvider(session_manager=mock_mgr, browser_runtime=mock_runtime)

    sub_res = await provider.subscribe(page_override=mock_runtime.default_page)
    assert sub_res.is_ok
    mock_mgr.execute_action.assert_awaited_with("youtube", "subscribe", {}, mock_runtime.default_page)

    mock_mgr.execute_action = AsyncMock(return_value=Ok({"action": "unsubscribe", "verified": True}))
    unsub_res = await provider.unsubscribe(page_override=mock_runtime.default_page)
    assert unsub_res.is_ok
    mock_mgr.execute_action.assert_awaited_with("youtube", "unsubscribe", {}, mock_runtime.default_page)


@pytest.mark.asyncio
async def test_youtube_close_tool():
    """Verify youtube_close_tool delegates to provider and returns proper message."""
    mock_provider = MagicMock(spec=YouTubeProvider)
    mock_provider.close = AsyncMock(
        return_value=Ok({"action": "close", "status": "closed", "message": "Closed YouTube tab. Other browser tabs remain open."})
    )
    set_youtube_provider(mock_provider)

    try:
        out = await youtube_close_tool({})
        assert "SUCCESS: Closed YouTube tab. Other browser tabs remain open." in out
    finally:
        set_youtube_provider(None)


@pytest.mark.asyncio
async def test_provider_close_delegation():
    """Verify YouTubeProvider.close untracks tab and resets extension runtime."""
    mock_runtime = MagicMock()
    mock_runtime.close_tab = AsyncMock(return_value={"ok": True, "status": "closed"})

    tracker = ActiveTabTracker()
    tracker.register_tab(target_id="tab_yt_99", url="https://www.youtube.com", label="youtube", app_type="youtube")

    provider = YouTubeProvider(tab_tracker=tracker, browser_runtime=mock_runtime)
    res = await provider.close()

    assert res.is_ok
    assert res.unwrap()["status"] == "closed"
    assert tracker.find_tab_by_app("youtube") is None
    mock_runtime.close_tab.assert_awaited_once_with(target_id="tab_yt_99")


def test_declarations_and_pipeline_registration():
    """Verify all 10 tools are declared and registered in CODING_TOOL_DECLARATIONS."""
    declared_names = {t["name"] for t in YOUTUBE_TOOL_DECLARATIONS}
    expected = {
        "youtube_play",
        "youtube_pause",
        "youtube_resume",
        "youtube_search",
        "youtube_skip_ad",
        "youtube_set_volume",
        "youtube_get_state",
        "youtube_subscribe",
        "youtube_unsubscribe",
        "youtube_close",
    }
    assert declared_names == expected

    from apps.desktop.src.jarvis_desktop.tool_pipeline import CODING_TOOL_DECLARATIONS, verify_tool_execution

    pipeline_tool_names = {t["name"] for t in CODING_TOOL_DECLARATIONS}
    for name in expected:
        assert name in pipeline_tool_names

    # Test verify_tool_execution
    outcome_ok = verify_tool_execution("youtube_play", {"query": "lofi"}, "SUCCESS: Playing 'lofi'")
    assert outcome_ok.verified is True

    outcome_err = verify_tool_execution("youtube_play", {"query": "lofi"}, "ERROR: Failed to play")
    assert outcome_err.verified is False

    outcome_sub = verify_tool_execution("youtube_subscribe", {}, "SUCCESS: Subscribed to channel")
    assert outcome_sub.verified is True

    outcome_unsub = verify_tool_execution("youtube_unsubscribe", {}, "SUCCESS: Unsubscribed from channel")
    assert outcome_unsub.verified is True

    outcome_close = verify_tool_execution("youtube_close", {}, "SUCCESS: Closed YouTube tab.")
    assert outcome_close.verified is True


@pytest.mark.asyncio
async def test_resubscription_toggle_flow():
    """Verify multi-turn resubscription sequence: subscribe -> unsubscribe -> resubscribe ('pheri subscribe')."""
    mock_mgr = MagicMock(spec=ApplicationSessionManager)
    mock_runtime = MockBrowserRuntime()
    provider = YouTubeProvider(session_manager=mock_mgr, browser_runtime=mock_runtime)

    # 1. First subscribe
    mock_mgr.execute_action = AsyncMock(
        return_value=Ok({
            "action": "subscribe",
            "channel": "Veritasium",
            "verified": True,
            "button_text": "Subscribed",
        })
    )
    res1 = await provider.subscribe(page_override=mock_runtime.default_page)
    assert res1.is_ok
    assert provider._session_memory.last_channel == "Veritasium"
    assert provider._session_memory.is_subscribed is True
    assert provider._session_memory.last_action == "subscribe"

    # 2. Unsubscribe
    mock_mgr.execute_action = AsyncMock(
        return_value=Ok({
            "action": "unsubscribe",
            "channel": "Veritasium",
            "verified": True,
            "button_text": "Subscribe",
        })
    )
    res2 = await provider.unsubscribe(page_override=mock_runtime.default_page)
    assert res2.is_ok
    assert provider._session_memory.last_channel == "Veritasium"
    assert provider._session_memory.is_subscribed is False
    assert provider._session_memory.last_action == "unsubscribe"

    # 3. Resubscribe ('pheri subscribe gara')
    mock_mgr.execute_action = AsyncMock(
        return_value=Ok({
            "action": "subscribe",
            "channel": "Veritasium",
            "verified": True,
            "button_text": "Subscribed",
        })
    )
    res3 = await provider.subscribe(page_override=mock_runtime.default_page)
    assert res3.is_ok
    assert provider._session_memory.last_channel == "Veritasium"
    assert provider._session_memory.is_subscribed is True
    assert provider._session_memory.last_action == "subscribe"


@pytest.mark.asyncio
async def test_already_subscribed_and_already_unsubscribed_precondition_idempotency():
    """Verify that subscribe and unsubscribe detect satisfied preconditions without redundant clicks."""
    mock_provider = MagicMock(spec=YouTubeProvider)
    mock_provider.subscribe = AsyncMock(
        return_value=Ok({
            "action": "subscribe",
            "already_subscribed": True,
            "channel": "Kurzgesagt",
            "button_text": "Subscribed",
        })
    )
    mock_provider.unsubscribe = AsyncMock(
        return_value=Ok({
            "action": "unsubscribe",
            "already_unsubscribed": True,
            "channel": "Kurzgesagt",
            "button_text": "Subscribe",
        })
    )
    set_youtube_provider(mock_provider)

    try:
        sub_out = await youtube_subscribe_tool({})
        assert "Already subscribed to channel 'Kurzgesagt'" in sub_out
        assert "[Precondition Satisfied]" in sub_out

        unsub_out = await youtube_unsubscribe_tool({})
        assert "Already unsubscribed from channel 'Kurzgesagt'" in unsub_out
        assert "[Precondition Satisfied]" in unsub_out
    finally:
        set_youtube_provider(None)


@pytest.mark.asyncio
async def test_youtube_get_state_perception():
    """Verify youtube_get_state_tool returns stage, channel, display status, and subscription state."""
    mock_provider = MagicMock(spec=YouTubeProvider)
    mock_provider.get_state = AsyncMock(
        return_value=Ok({
            "display_open": True,
            "running": True,
            "page_stage": "channel",
            "channel_name": "Marques Brownlee",
            "is_subscribed": True,
            "subscription_button_text": "Subscribed",
            "video_title": "",
            "playback": {"found": False},
            "session_memory": {
                "last_channel": "Marques Brownlee",
                "last_action": "subscribe",
                "is_subscribed": True,
            },
        })
    )
    set_youtube_provider(mock_provider)

    try:
        state_out = await youtube_get_state_tool({})
        assert "Display Open=True" in state_out
        assert "Stage='channel'" in state_out
        assert "Channel='Marques Brownlee'" in state_out
        assert "Subscription=Subscribed ('Subscribed')" in state_out
        assert "Last Action='subscribe'" in state_out
    finally:
        set_youtube_provider(None)

