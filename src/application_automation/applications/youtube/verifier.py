"""jarvis.application_automation.applications.youtube.verifier — Real DOM playback verification.

Inspects HTML5 <video> elements directly to guarantee ground truth on video playback state.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict

from ...action_verifier import ActionVerificationResult

MEDIA_PROPERTIES_SCRIPT = """
() => {
    const video = document.querySelector('video.html5-main-video') || document.querySelector('video');
    if (!video) {
        return { found: false };
    }
    let title = '';
    const titleEl = document.querySelector('h1.ytd-watch-metadata yt-formatted-string') ||
                    document.querySelector('h1.title') ||
                    document.querySelector('#title h1');
    if (titleEl) {
        title = titleEl.textContent ? titleEl.textContent.trim() : '';
    } else {
        title = document.title.replace(' - YouTube', '').trim();
    }

    return {
        found: true,
        paused: video.paused,
        currentTime: video.currentTime,
        duration: video.duration,
        ended: video.ended,
        readyState: video.readyState,
        volume: video.volume,
        muted: video.muted,
        title: title
    };
}
"""


class YouTubeVerifier:
    """Verifies playback, pause, and navigation outcomes on YouTube pages."""

    @staticmethod
    async def get_playback_metrics(page: Any) -> Dict[str, Any]:
        """Query real HTML5 video metrics from the active page."""
        try:
            res = await page.evaluate(MEDIA_PROPERTIES_SCRIPT)
            return res if isinstance(res, dict) else {"found": False}
        except Exception as e:
            return {"found": False, "error": str(e)}

    @classmethod
    async def verify_playback(
        cls,
        page: Any,
        expect_playing: bool = True,
        sample_interval: float = 0.3,
    ) -> ActionVerificationResult:
        """Verify whether video is actively rendering frames / playing."""
        m1 = await cls.get_playback_metrics(page)
        if not m1.get("found"):
            return ActionVerificationResult.suspected_noop(
                action_name="verify_playback",
                reason="No HTML5 <video> element found on current YouTube page.",
                details=m1,
            )

        # Check pause state
        is_paused = m1.get("paused", True)
        if expect_playing and is_paused:
            # Video is paused when we expected playing
            return ActionVerificationResult.suspected_noop(
                action_name="verify_playback",
                reason="Video element is paused (expected playing).",
                details=m1,
            )

        if not expect_playing and not is_paused:
            # Video is playing when we expected paused
            return ActionVerificationResult.suspected_noop(
                action_name="verify_playback",
                reason="Video element is playing (expected paused).",
                details=m1,
            )

        # If expecting playing, take a second sample to verify currentTime advancement
        if expect_playing:
            t1 = m1.get("currentTime", 0.0)
            await asyncio.sleep(sample_interval)
            m2 = await cls.get_playback_metrics(page)
            t2 = m2.get("currentTime", 0.0)

            # Either currentTime progressed or video is at ended/buffering with readyState >= 3
            if t2 > t1 or m2.get("readyState", 0) >= 3:
                return ActionVerificationResult.confirmed(
                    action_name="verify_playback",
                    details={
                        "title": m2.get("title") or m1.get("title"),
                        "currentTime": t2,
                        "duration": m2.get("duration"),
                        "paused": False,
                        "time_advanced": t2 > t1,
                    },
                )
            else:
                return ActionVerificationResult.unverifiable(
                    action_name="verify_playback",
                    reason="Video was unpaused but playback position did not advance (may be buffering).",
                    details={"initial_metrics": m1, "second_metrics": m2},
                )

        return ActionVerificationResult.confirmed(
            action_name="verify_playback",
            details={"paused": True, "currentTime": m1.get("currentTime")},
        )

    @classmethod
    async def verify_subscription(
        cls,
        page: Any,
        expect_subscribed: bool = True,
    ) -> ActionVerificationResult:
        """Verify whether channel subscription state changed on the active page."""
        try:
            from .actions import YouTubeActions

            state = await YouTubeActions.get_live_channel_state(page)
            is_sub = bool(state.get("is_subscribed"))
            ch_name = state.get("channel_name") or "channel"
            btn_txt = state.get("button_text", "")

            if expect_subscribed and is_sub:
                return ActionVerificationResult.confirmed(
                    action_name="verify_subscription",
                    details={"subscribed": True, "channel_name": ch_name, "button_text": btn_txt},
                )
            elif not expect_subscribed and not is_sub:
                return ActionVerificationResult.confirmed(
                    action_name="verify_subscription",
                    details={"subscribed": False, "channel_name": ch_name, "button_text": btn_txt},
                )
            else:
                return ActionVerificationResult.suspected_noop(
                    action_name="verify_subscription",
                    reason=f"Expected subscription={expect_subscribed}, but button indicates subscribed={is_sub} (channel: '{ch_name}', text: '{btn_txt}').",
                    details=state,
                )
        except Exception as e:
            return ActionVerificationResult.unverifiable(
                action_name="verify_subscription",
                reason=f"Error evaluating subscription state: {e}",
            )

