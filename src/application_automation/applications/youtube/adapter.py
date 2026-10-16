"""jarvis.application_automation.applications.youtube.adapter — YouTube application adapter.

Orchestrates the YouTube state machine, resilient locators, high-level action execution,
real playback verification, and interstitial recovery.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from jarvis_sdk import Err, Ok, Result

from ...action_verifier import ActionVerificationResult
from ..base import BaseApplicationAdapter
from .actions import YouTubeActions
from .recovery import YouTubeRecoveryHandler
from .state_machine import (
    STATE_HOME,
    STATE_SEARCH_RESULTS,
    STATE_SEARCHING,
    STATE_UNINITIALIZED,
    STATE_VIDEO_PAUSED,
    STATE_VIDEO_PLAYING,
    STATE_WATCH_PAGE,
    YouTubeStateMachine,
)
from .verifier import YouTubeVerifier


class YouTubeAdapter(BaseApplicationAdapter):
    """Production-grade automation adapter for YouTube."""

    def __init__(self) -> None:
        self.state_machine = YouTubeStateMachine()
        self.actions = YouTubeActions()
        self.verifier = YouTubeVerifier()
        self.recovery = YouTubeRecoveryHandler()

    @property
    def app_name(self) -> str:
        return "youtube"

    def can_handle(self, url: str, app_name: Optional[str] = None) -> bool:
        if app_name and app_name.lower() in ("youtube", "yt"):
            return True
        if url and ("youtube.com" in url.lower() or "youtu.be" in url.lower()):
            return True
        return False

    def get_current_state(self) -> str:
        return self.state_machine.current_state

    def sync_state_from_url(self, url: str) -> str:
        """Infer and sync state from current page URL."""
        if not url:
            new_state = STATE_UNINITIALIZED
        elif "/watch" in url:
            new_state = STATE_WATCH_PAGE
        elif "/results" in url:
            new_state = STATE_SEARCH_RESULTS
        elif "youtube.com" in url:
            new_state = STATE_HOME
        else:
            new_state = STATE_UNINITIALIZED

        self.state_machine.transition_to(new_state, trigger="url_sync", force=True)
        return new_state

    async def handle_interstitials(self, page: Any) -> bool:
        """Dismiss consent dialogs, promo modals, and skippable ads."""
        return await self.recovery.handle_all_interstitials(page)

    async def get_playback_status(self, page: Any) -> Dict[str, Any]:
        """Fetch current media playback information."""
        return await self.actions.get_playback_status(page)

    async def execute_action(
        self,
        action: str,
        params: Dict[str, Any],
        page: Any,
    ) -> Result[Dict[str, Any]]:
        """Dispatch action to YouTube action handlers and transition state."""
        clean_action = action.strip().lower()
        self.sync_state_from_url(getattr(page, "url", ""))

        # ── 1. Search & Play Composite Action ──
        if clean_action in ("search_and_play", "play_query"):
            query = params.get("query", "")
            if not query:
                return Err("Missing 'query' parameter for search_and_play", code="INVALID_ARGUMENT")

            self.state_machine.transition_to(STATE_SEARCHING, trigger="search_start", force=True)
            search_res = await self.actions.search(page, query)
            if not search_res.is_ok:
                return search_res

            self.state_machine.transition_to(STATE_SEARCH_RESULTS, trigger="search_complete", force=True)
            play_res = await self.actions.play_first_result(page)
            if not play_res.is_ok:
                return play_res

            self.state_machine.transition_to(STATE_VIDEO_PLAYING, trigger="video_started", force=True)
            return Ok({
                "action": "search_and_play",
                "query": query,
                "video_title": play_res.unwrap().get("title"),
                "url": page.url,
            })

        # ── 2. Search ──
        elif clean_action == "search":
            query = params.get("query", "")
            self.state_machine.transition_to(STATE_SEARCHING, trigger="search_start", force=True)
            res = await self.actions.search(page, query)
            if res.is_ok:
                self.state_machine.transition_to(STATE_SEARCH_RESULTS, trigger="search_complete", force=True)
            return res

        # ── 3. Play Result ──
        elif clean_action in ("play_first_result", "play_first"):
            res = await self.actions.play_first_result(page)
            if res.is_ok:
                self.state_machine.transition_to(STATE_VIDEO_PLAYING, trigger="play_result", force=True)
            return res

        elif clean_action in ("play_video_by_title", "play_title"):
            title = params.get("title", "")
            res = await self.actions.play_video_by_title(page, title)
            if res.is_ok:
                self.state_machine.transition_to(STATE_VIDEO_PLAYING, trigger="play_title", force=True)
            return res

        # ── 4. Playback Controls ──
        elif clean_action in ("pause", "stop"):
            res = await self.actions.pause(page)
            if res.is_ok:
                self.state_machine.transition_to(STATE_VIDEO_PAUSED, trigger="pause", force=True)
            return res

        elif clean_action in ("resume", "play"):
            res = await self.actions.resume(page)
            if res.is_ok:
                self.state_machine.transition_to(STATE_VIDEO_PLAYING, trigger="resume", force=True)
            return res

        elif clean_action == "toggle_play":
            return await self.actions.toggle_play(page)

        # ── 5. Ads ──
        elif clean_action == "skip_ad":
            return await self.actions.skip_ad(page)

        # ── 6. Audio / Volume ──
        elif clean_action in ("volume_up", "louder"):
            step = params.get("step", 10)
            return await self.actions.adjust_volume(page, delta=int(step))

        elif clean_action in ("volume_down", "softer"):
            step = params.get("step", 10)
            return await self.actions.adjust_volume(page, delta=-int(step))

        elif clean_action == "set_volume":
            vol = params.get("volume", 50)
            return await self.actions.set_volume(page, volume=int(vol))

        elif clean_action == "mute":
            return await self.actions.mute(page)

        elif clean_action == "unmute":
            return await self.actions.unmute(page)

        elif clean_action in ("status", "playback_status"):
            metrics = await self.actions.get_playback_status(page)
            return Ok(metrics)

        # ── 7. Subscription Controls (OpenClaw Parity) ──
        elif clean_action == "subscribe":
            return await self.actions.subscribe(page)

        elif clean_action == "unsubscribe":
            return await self.actions.unsubscribe(page)

        elif clean_action in ("check_subscription", "subscription_state"):
            state = await self.actions.check_subscription_state(page)
            return Ok(state)

        return Err(f"Unsupported YouTube action: '{action}'", code="UNSUPPORTED_ACTION")

    async def verify_action(
        self,
        action: str,
        params: Dict[str, Any],
        page: Any,
    ) -> ActionVerificationResult:
        """Inspect actual DOM/player outcome following OpenClaw precedence."""
        clean_action = action.strip().lower()

        # Subscription verification (OpenClaw Parity)
        if clean_action == "subscribe":
            return await self.verifier.verify_subscription(page, expect_subscribed=True)

        if clean_action == "unsubscribe":
            return await self.verifier.verify_subscription(page, expect_subscribed=False)

        # Playback verification (play, resume, search_and_play)
        if clean_action in ("search_and_play", "play_query", "play_first_result", "play_first", "resume", "play"):
            return await self.verifier.verify_playback(page, expect_playing=True)

        # Pause verification
        if clean_action in ("pause", "stop"):
            return await self.verifier.verify_playback(page, expect_playing=False)

        # Search verification: URL should contain /results or searchbox should reflect query
        if clean_action == "search":
            url = getattr(page, "url", "")
            if "/results" in url:
                return ActionVerificationResult.confirmed("search", {"url": url})
            return ActionVerificationResult.unverifiable("search", "Page URL does not indicate search results.")

        # Audio volume verification
        if clean_action in ("set_volume", "volume_up", "volume_down", "mute", "unmute"):
            metrics = await self.verifier.get_playback_metrics(page)
            if metrics.get("found"):
                return ActionVerificationResult.confirmed(clean_action, {"volume": metrics.get("volume"), "muted": metrics.get("muted")})
            return ActionVerificationResult.unverifiable(clean_action, "Could not read volume from video element.")

        # Default fallback verification
        return ActionVerificationResult.confirmed(clean_action, {"status": "executed"})

