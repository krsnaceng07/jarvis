"""tests.test_youtube_adapter_parity — Parity test suite for YouTube Application Adapter.

Validates:
1. YouTubeStateMachine: lifecycle states and transition integrity.
2. YouTubeVerifier: real HTML5 <video> evaluation and mutation precedence.
3. YouTubeRecoveryHandler: Google cookie consent, promo modal, and ad dismissers.
4. YouTubeActions: multi-tier locator resolution and JavaScript fallback.
5. YouTubeAdapter: contract compliance, composite search_and_play, and state synchronization.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
import pytest

from src.application_automation.action_verifier import ActionEffect
from src.application_automation.applications.youtube import (
    YouTubeAdapter,
    YouTubeRecoveryHandler,
    YouTubeStateMachine,
    YouTubeVerifier,
)
from src.application_automation.applications.youtube.state_machine import (
    STATE_HOME,
    STATE_SEARCH_RESULTS,
    STATE_SEARCHING,
    STATE_VIDEO_PAUSED,
    STATE_VIDEO_PLAYING,
    STATE_WATCH_PAGE,
)


class TestYouTubeStateMachineParity:
    """Validates YouTube finite state machine transitions."""

    def test_state_machine_happy_path(self) -> None:
        sm = YouTubeStateMachine()
        assert sm.current_state == "UNINITIALIZED"

        assert sm.transition_to(STATE_HOME, trigger="open")
        assert sm.current_state == STATE_HOME

        assert sm.transition_to(STATE_SEARCHING, trigger="search_input")
        assert sm.current_state == STATE_SEARCHING

        assert sm.transition_to(STATE_SEARCH_RESULTS, trigger="search_submit")
        assert sm.current_state == STATE_SEARCH_RESULTS

        assert sm.transition_to(STATE_WATCH_PAGE, trigger="click_video")
        assert sm.current_state == STATE_WATCH_PAGE

        assert sm.transition_to(STATE_VIDEO_PLAYING, trigger="playback_started")
        assert sm.current_state == STATE_VIDEO_PLAYING

        assert sm.transition_to(STATE_VIDEO_PAUSED, trigger="pause")
        assert sm.current_state == STATE_VIDEO_PAUSED

        assert sm.transition_to(STATE_VIDEO_PLAYING, trigger="resume")
        assert sm.current_state == STATE_VIDEO_PLAYING


class TestYouTubeVerifierParity:
    """Validates HTML5 <video> property verification and mutation precedence."""

    @pytest.mark.asyncio
    async def test_verify_playback_confirmed_when_playing_and_advancing(self) -> None:
        mock_page = MagicMock()
        # First call: currentTime = 10.0, paused = False
        # Second call: currentTime = 10.5, paused = False
        mock_page.evaluate = AsyncMock(side_effect=[
            {"found": True, "paused": False, "currentTime": 10.0, "duration": 200.0, "readyState": 4, "title": "Believer"},
            {"found": True, "paused": False, "currentTime": 10.5, "duration": 200.0, "readyState": 4, "title": "Believer"},
        ])

        res = await YouTubeVerifier.verify_playback(mock_page, expect_playing=True, sample_interval=0.01)
        assert res.effect == ActionEffect.CONFIRMED
        assert res.verified is True
        assert res.details["paused"] is False
        assert res.details["title"] == "Believer"

    @pytest.mark.asyncio
    async def test_verify_playback_suspected_noop_when_paused(self) -> None:
        mock_page = MagicMock()
        mock_page.evaluate = AsyncMock(return_value={
            "found": True, "paused": True, "currentTime": 10.0, "duration": 200.0, "readyState": 4, "title": "Believer"
        })

        res = await YouTubeVerifier.verify_playback(mock_page, expect_playing=True)
        assert res.effect == ActionEffect.SUSPECTED_NOOP
        assert res.verified is False
        assert "paused" in str(res.error)

    @pytest.mark.asyncio
    async def test_verify_playback_suspected_noop_when_no_video_element(self) -> None:
        mock_page = MagicMock()
        mock_page.evaluate = AsyncMock(return_value={"found": False})

        res = await YouTubeVerifier.verify_playback(mock_page, expect_playing=True)
        assert res.effect == ActionEffect.SUSPECTED_NOOP
        assert res.verified is False


class TestYouTubeRecoveryHandlerParity:
    """Validates interstitial interceptors and dismissers."""

    @pytest.mark.asyncio
    async def test_dismiss_cookie_consent_when_present(self) -> None:
        mock_button = MagicMock()
        mock_button.is_visible = AsyncMock(return_value=True)
        mock_button.click = AsyncMock()

        mock_page = MagicMock()
        mock_page.query_selector = AsyncMock(return_value=mock_button)

        dismissed = await YouTubeRecoveryHandler.dismiss_cookie_consent(mock_page)
        assert dismissed is True
        mock_button.click.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_dismiss_premium_dialog_when_present(self) -> None:
        mock_button = MagicMock()
        mock_button.is_visible = AsyncMock(return_value=True)
        mock_button.click = AsyncMock()

        mock_page = MagicMock()
        mock_page.query_selector = AsyncMock(return_value=mock_button)

        dismissed = await YouTubeRecoveryHandler.dismiss_premium_dialog(mock_page)
        assert dismissed is True
        mock_button.click.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_handle_advertisements_skips_when_button_visible(self) -> None:
        mock_skip_btn = MagicMock()
        mock_skip_btn.is_visible = AsyncMock(return_value=True)
        mock_skip_btn.click = AsyncMock()

        mock_page = MagicMock()
        mock_page.query_selector = AsyncMock(return_value=mock_skip_btn)

        res = await YouTubeRecoveryHandler.handle_advertisements(mock_page)
        assert res.get("ad_active") is True
        assert res.get("skipped") is True
        mock_skip_btn.click.assert_awaited_once()


class TestYouTubeAdapterParity:
    """Validates YouTubeAdapter contract compliance, action dispatch, and state tracking."""

    def test_can_handle_url_and_app_name(self) -> None:
        adapter = YouTubeAdapter()
        assert adapter.can_handle("https://www.youtube.com") is True
        assert adapter.can_handle("https://youtu.be/dQw4w9WgXcQ") is True
        assert adapter.can_handle("", app_name="youtube") is True
        assert adapter.can_handle("https://google.com") is False

    def test_sync_state_from_url(self) -> None:
        adapter = YouTubeAdapter()
        assert adapter.sync_state_from_url("https://www.youtube.com") == STATE_HOME
        assert adapter.sync_state_from_url("https://www.youtube.com/results?search_query=test") == STATE_SEARCH_RESULTS
        assert adapter.sync_state_from_url("https://www.youtube.com/watch?v=123") == STATE_WATCH_PAGE

    @pytest.mark.asyncio
    async def test_execute_search_and_play(self) -> None:
        adapter = YouTubeAdapter()
        mock_page = MagicMock()
        mock_page.url = "https://www.youtube.com/watch?v=test"

        # Mock search input element
        mock_input = MagicMock()
        mock_input.is_visible = AsyncMock(return_value=True)
        mock_input.click = AsyncMock()
        mock_input.fill = AsyncMock()
        mock_input.press = AsyncMock()

        # Mock video title link in search results
        mock_video_link = MagicMock()
        mock_video_link.is_visible = AsyncMock(return_value=True)
        mock_video_link.text_content = AsyncMock(return_value="Imagine Dragons - Believer (Official Music Video)")
        mock_video_link.click = AsyncMock()

        # Wire query_selector to return input on first search selector, then video link on results selector
        def mock_qs(selector: str):
            if "search" in selector.lower():
                return mock_input
            if "video-title" in selector.lower():
                return mock_video_link
            return None

        mock_page.query_selector = AsyncMock(side_effect=mock_qs)
        mock_page.evaluate = AsyncMock(return_value={"found": True, "paused": False, "currentTime": 1.0, "title": "Believer"})

        res = await adapter.execute_action("search_and_play", {"query": "Believer"}, mock_page)
        assert res.is_ok
        payload = res.unwrap()
        assert payload["action"] == "search_and_play"
        assert payload["query"] == "Believer"
        assert "Believer" in payload["video_title"]
        assert adapter.get_current_state() == STATE_VIDEO_PLAYING

    @pytest.mark.asyncio
    async def test_execute_pause_and_resume(self) -> None:
        adapter = YouTubeAdapter()
        mock_page = MagicMock()
        mock_page.url = "https://www.youtube.com/watch?v=123"

        # Pause call evaluates JS and returns paused: true
        mock_page.evaluate = AsyncMock(return_value={"paused": True})
        res_pause = await adapter.execute_action("pause", {}, mock_page)
        assert res_pause.is_ok
        assert adapter.get_current_state() == STATE_VIDEO_PAUSED

        # Resume call evaluates JS and returns paused: false
        mock_page.evaluate = AsyncMock(return_value={"paused": False})
        res_resume = await adapter.execute_action("resume", {}, mock_page)
        assert res_resume.is_ok
        assert adapter.get_current_state() == STATE_VIDEO_PLAYING

    @pytest.mark.asyncio
    async def test_execute_subscribe_and_unsubscribe_with_verification(self) -> None:
        """Verify subscribe and unsubscribe actions execute and verify properly."""
        adapter = YouTubeAdapter()
        mock_page = MagicMock()
        mock_page.url = "https://www.youtube.com/@veritasium"

        # Subscription state returns false (not subscribed yet)
        mock_btn = MagicMock()
        mock_btn.is_visible = AsyncMock(return_value=True)
        mock_btn.inner_text = AsyncMock(return_value="Subscribe")
        mock_btn.get_attribute = AsyncMock(return_value="Subscribe to channel")
        mock_btn.click = AsyncMock()
        mock_page.query_selector = AsyncMock(return_value=mock_btn)
        mock_page.evaluate = AsyncMock(side_effect=[
            # check_subscription_state before subscribe
            {"found": True, "is_subscribed": False, "text": "Subscribe"},
            # verify_subscription after subscribe
            {"found": True, "is_subscribed": True, "text": "Subscribed"},
        ])

        sub_res = await adapter.execute_action("subscribe", {}, mock_page)
        assert sub_res.is_ok
        assert sub_res.unwrap()["action"] == "subscribe"

        verif_sub = await adapter.verify_action("subscribe", {}, mock_page)
        assert verif_sub.verified is True

        # Now test unsubscribe with multi-tier interaction
        mock_sub_btn = MagicMock()
        mock_sub_btn.is_visible = AsyncMock(return_value=True)
        mock_sub_btn.click = AsyncMock()

        mock_menu_item = MagicMock()
        mock_menu_item.is_visible = AsyncMock(return_value=True)
        mock_menu_item.click = AsyncMock()

        mock_dialog_confirm = MagicMock()
        mock_dialog_confirm.is_visible = AsyncMock(return_value=True)
        mock_dialog_confirm.click = AsyncMock()

        def mock_qs_unsub(sel: str):
            if "subscribed" in sel.lower():
                return mock_sub_btn
            if "menu" in sel.lower() or "item" in sel.lower():
                return mock_menu_item
            if "confirm" in sel.lower():
                return mock_dialog_confirm
            return None

        mock_page.query_selector = AsyncMock(side_effect=mock_qs_unsub)
        mock_page.evaluate = AsyncMock(side_effect=[
            # check_subscription_state before unsubscribe -> currently subscribed
            {"found": True, "is_subscribed": True, "text": "Subscribed"},
            # check_subscription_state after unsubscribe -> no longer subscribed!
            {"found": True, "is_subscribed": False, "text": "Subscribe"},
            # verify_subscription after unsubscribe
            {"found": True, "is_subscribed": False, "text": "Subscribe"},
        ])

        unsub_res = await adapter.execute_action("unsubscribe", {}, mock_page)
        assert unsub_res.is_ok
        unsub_data = unsub_res.unwrap()
        assert unsub_data["action"] == "unsubscribe"
        assert unsub_data["clicked"] is True
        assert unsub_data["menu_clicked"] is True
        assert unsub_data["modal_confirmed"] is True
        assert unsub_data["verified"] is True

        verif_unsub = await adapter.verify_action("unsubscribe", {}, mock_page)
        assert verif_unsub.verified is True
