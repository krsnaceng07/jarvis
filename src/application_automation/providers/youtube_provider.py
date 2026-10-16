"""jarvis.application_automation.providers.youtube_provider — Production YouTube automation provider.

OpenClaw parity:
- Implements provider contract isolating YouTube automation capabilities from transports/LLM.
- Preserves tab affinity via ActiveTabTracker: reuses existing tabs without destructive reloads.
- Enforces HTML5 media verification (video element inspect) before reporting success.
- Automatically handles cookie consent dialogs and video advertisement interstitials.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

from jarvis_sdk import Err, Ok, Result

from ..active_tab_tracker import ActiveTabTracker
from ..application_session_manager import ApplicationSessionManager
from ..applications.youtube.adapter import YouTubeAdapter


@dataclass(slots=True)
class YouTubeSessionMemory:
    """Multi-turn session memory for YouTube operations."""

    last_channel: str = ""
    last_action: str = ""
    is_subscribed: Optional[bool] = None
    last_action_timestamp: float = 0.0
    active_page_stage: str = "unknown"


class YouTubeProvider:
    """Production-grade YouTube capability provider following OpenClaw architecture."""

    app_id: str = "youtube"
    app_name: str = "YouTube"

    def __init__(
        self,
        session_manager: Optional[ApplicationSessionManager] = None,
        tab_tracker: Optional[ActiveTabTracker] = None,
        browser_runtime: Optional[Any] = None,
    ) -> None:
        self._session_manager = session_manager or ApplicationSessionManager.get_instance()
        self._tab_tracker = tab_tracker or ActiveTabTracker.get_instance()
        self._browser_runtime = browser_runtime
        self._session_memory = YouTubeSessionMemory()
        self._adapter = self._session_manager.get_adapter("youtube")
        if not self._adapter or not isinstance(self._adapter, YouTubeAdapter):
            self._adapter = YouTubeAdapter()
            self._session_manager.register_adapter(self._adapter)

    @property
    def session_memory(self) -> YouTubeSessionMemory:
        """Return the multi-turn session memory snapshot."""
        return self._session_memory

    async def _get_runtime(self) -> Any:
        if self._browser_runtime is not None:
            return self._browser_runtime
        try:
            from extensions.browser.src.browser_runtime import get_browser_runtime

            self._browser_runtime = await get_browser_runtime()
            return self._browser_runtime
        except Exception:
            return None

    async def ensure_active_page(self, page_override: Optional[Any] = None) -> Any:
        """Acquire or activate YouTube page, honoring tab affinity to prevent duplicate tabs."""
        if page_override is not None:
            return page_override

        runtime = await self._get_runtime()
        if runtime is None:
            raise RuntimeError("Browser runtime is not available.")

        # 1. Check ActiveTabTracker for existing YouTube tab
        tracked_tab = self._tab_tracker.find_tab_by_app("youtube")
        if not tracked_tab:
            tracked_tab = self._tab_tracker.find_tab_by_domain("youtube.com")

        if tracked_tab:
            try:
                page = await runtime.get_page(target_id=tracked_tab.target_id)
                if page and not getattr(page, "is_closed", lambda: False)():
                    try:
                        await page.bring_to_front()
                    except Exception:
                        pass
                    return page
            except Exception:
                pass

        # 1b. Check all open tabs in browser runtime to adopt existing YouTube page without opening new tab
        try:
            open_tabs = await runtime.list_tabs()
            for t in open_tabs:
                url = t.get("url", "").lower()
                if "youtube.com" in url or "youtu.be" in url:
                    tid = t.get("targetId")
                    if tid:
                        page = await runtime.get_page(target_id=tid)
                        if page and not getattr(page, "is_closed", lambda: False)():
                            self._tab_tracker.register_tab(
                                target_id=tid,
                                url=t.get("url", ""),
                                title=t.get("title", "YouTube"),
                                label="youtube",
                                tab_id=tid,
                            )
                            try:
                                await page.bring_to_front()
                            except Exception:
                                pass
                            return page
        except Exception:
            pass

        # 2. Open tab or reuse matching label without reloading
        tab_info = await runtime.open_tab(url="https://www.youtube.com", label="youtube")
        target_id = tab_info.get("targetId", "youtube")
        page = await runtime.get_page(target_id=target_id)
        self._tab_tracker.register_tab(
            target_id=target_id,
            url=getattr(page, "url", "https://www.youtube.com"),
            title=getattr(page, "title", lambda: "")() if not asyncio.iscoroutinefunction(getattr(page, "title", None)) else "YouTube",
            label="youtube",
            tab_id=target_id,
        )
        return page

    def _sync_extension_runtime(
        self,
        is_playing: bool,
        active_video: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Update extension runtime singleton if available."""
        try:
            from extensions.youtube.runtime import YouTubeRuntime, get_youtube_runtime, set_youtube_runtime

            rt = get_youtube_runtime()
            if rt is None:
                rt = YouTubeRuntime()
            rt.started = True
            rt.is_playing = is_playing
            if active_video:
                rt.active_video = active_video
            rt.last_action_at_ms = int(time.time() * 1000)
            if metadata:
                rt.metadata.update(metadata)
            set_youtube_runtime(rt)
        except Exception:
            pass

    async def play(
        self,
        query: str = "",
        title: str = "",
        page_override: Optional[Any] = None,
    ) -> Result[Dict[str, Any]]:
        """Search and play a video, or resume playback if no query/title given."""
        try:
            page = await self.ensure_active_page(page_override=page_override)
        except Exception as e:
            return Err(f"Failed to acquire YouTube page: {e}", code="BROWSER_UNAVAILABLE")

        clean_query = query.strip()
        clean_title = title.strip()

        if clean_query:
            action = "search_and_play"
            params = {"query": clean_query}
        elif clean_title:
            action = "play_video_by_title"
            params = {"title": clean_title}
        else:
            action = "resume"
            params = {}

        res = await self._session_manager.execute_action("youtube", action, params, page)
        if res.is_ok:
            payload = res.unwrap()
            v_title = payload.get("video_title") or payload.get("title") or clean_query or clean_title
            self._sync_extension_runtime(is_playing=True, active_video=v_title, metadata=payload)
        return res

    async def pause(self, page_override: Optional[Any] = None) -> Result[Dict[str, Any]]:
        """Pause active YouTube video playback."""
        try:
            page = await self.ensure_active_page(page_override=page_override)
        except Exception as e:
            return Err(f"Failed to acquire YouTube page: {e}", code="BROWSER_UNAVAILABLE")

        res = await self._session_manager.execute_action("youtube", "pause", {}, page)
        if res.is_ok:
            self._sync_extension_runtime(is_playing=False)
        return res

    async def resume(self, page_override: Optional[Any] = None) -> Result[Dict[str, Any]]:
        """Resume paused YouTube video playback."""
        try:
            page = await self.ensure_active_page(page_override=page_override)
        except Exception as e:
            return Err(f"Failed to acquire YouTube page: {e}", code="BROWSER_UNAVAILABLE")

        res = await self._session_manager.execute_action("youtube", "resume", {}, page)
        if res.is_ok:
            self._sync_extension_runtime(is_playing=True)
        return res

    async def search(
        self,
        query: str,
        page_override: Optional[Any] = None,
    ) -> Result[Dict[str, Any]]:
        """Search YouTube for query without auto-playing first result."""
        clean_query = query.strip()
        if not clean_query:
            return Err("Search query cannot be empty", code="INVALID_ARGUMENT")

        try:
            page = await self.ensure_active_page(page_override=page_override)
        except Exception as e:
            return Err(f"Failed to acquire YouTube page: {e}", code="BROWSER_UNAVAILABLE")

        return await self._session_manager.execute_action(
            "youtube", "search", {"query": clean_query}, page
        )

    async def skip_ad(self, page_override: Optional[Any] = None) -> Result[Dict[str, Any]]:
        """Skip currently active video advertisement."""
        try:
            page = await self.ensure_active_page(page_override=page_override)
        except Exception as e:
            return Err(f"Failed to acquire YouTube page: {e}", code="BROWSER_UNAVAILABLE")

        return await self._session_manager.execute_action("youtube", "skip_ad", {}, page)

    async def set_volume(
        self,
        volume: int,
        page_override: Optional[Any] = None,
    ) -> Result[Dict[str, Any]]:
        """Set YouTube video volume (0-100)."""
        clamped = max(0, min(100, int(volume)))
        try:
            page = await self.ensure_active_page(page_override=page_override)
        except Exception as e:
            return Err(f"Failed to acquire YouTube page: {e}", code="BROWSER_UNAVAILABLE")

        return await self._session_manager.execute_action(
            "youtube", "set_volume", {"volume": clamped}, page
        )

    async def get_state(self, page_override: Optional[Any] = None) -> Result[Dict[str, Any]]:
        """Get live display status, page stage, channel info, subscription status, and playback metrics."""
        runtime = await self._get_runtime()
        display_open = False
        if runtime is not None:
            try:
                open_tabs = await runtime.list_tabs()
                display_open = any("youtube.com" in t.get("url", "").lower() or "youtu.be" in t.get("url", "").lower() for t in open_tabs)
            except Exception:
                pass

        try:
            page = await self.ensure_active_page(page_override=page_override)
        except Exception as e:
            return Ok({
                "display_open": False,
                "running": False,
                "found": False,
                "is_playing": False,
                "session_memory": {
                    "last_channel": self._session_memory.last_channel,
                    "last_action": self._session_memory.last_action,
                    "is_subscribed": self._session_memory.is_subscribed,
                },
                "detail": str(e),
            })

        if getattr(page, "is_closed", lambda: False)():
            return Ok({
                "display_open": False,
                "running": False,
                "found": False,
                "is_playing": False,
                "session_memory": {
                    "last_channel": self._session_memory.last_channel,
                    "last_action": self._session_memory.last_action,
                    "is_subscribed": self._session_memory.is_subscribed,
                },
            })

        # Fetch playback metrics
        playback_res = await self._session_manager.execute_action("youtube", "playback_status", {}, page)
        playback_data = playback_res.unwrap() if playback_res.is_ok else {}

        # Fetch channel and page stage state
        from ..applications.youtube.actions import YouTubeActions

        channel_state = await YouTubeActions.get_live_channel_state(page)

        # Update session memory
        if channel_state.get("channel_name"):
            self._session_memory.last_channel = channel_state.get("channel_name")
        self._session_memory.is_subscribed = channel_state.get("is_subscribed")
        self._session_memory.active_page_stage = channel_state.get("page_stage", "unknown")

        return Ok({
            "display_open": True,
            "running": True,
            "page_stage": channel_state.get("page_stage", "unknown"),
            "channel_name": channel_state.get("channel_name", ""),
            "is_subscribed": channel_state.get("is_subscribed", False),
            "subscription_button_text": channel_state.get("button_text", ""),
            "subscription_button_found": channel_state.get("found", False),
            "playback": playback_data,
            "is_playing": playback_data.get("found") and not playback_data.get("paused"),
            "video_title": playback_data.get("title", ""),
            "session_memory": {
                "last_channel": self._session_memory.last_channel,
                "last_action": self._session_memory.last_action,
                "is_subscribed": self._session_memory.is_subscribed,
                "last_action_timestamp": self._session_memory.last_action_timestamp,
            },
        })

    async def subscribe(self, page_override: Optional[Any] = None) -> Result[Dict[str, Any]]:
        """Subscribe to the channel on the active YouTube page with session memory tracking."""
        try:
            page = await self.ensure_active_page(page_override=page_override)
        except Exception as e:
            return Err(f"Failed to acquire YouTube page: {e}", code="BROWSER_UNAVAILABLE")

        res = await self._session_manager.execute_action("youtube", "subscribe", {}, page)
        if res.is_ok:
            data = res.unwrap()
            ch = data.get("channel") or self._session_memory.last_channel
            self._session_memory.last_channel = ch
            self._session_memory.last_action = "subscribe"
            self._session_memory.is_subscribed = True
            self._session_memory.last_action_timestamp = time.time()
            data["session_memory"] = {
                "last_channel": ch,
                "last_action": "subscribe",
                "is_subscribed": True,
            }
            try:
                from src.agents.task.runtime_state import RuntimeStateManager

                r_state = RuntimeStateManager.get_instance()
                r_state.set_active_browser_context(
                    target_id="youtube",
                    url=getattr(page, "url", ""),
                    title=ch or getattr(page, "title", lambda: "")(),
                    page_type="channel",
                    page_state="subscribed",
                )
            except Exception:
                pass
        return res

    async def unsubscribe(self, page_override: Optional[Any] = None) -> Result[Dict[str, Any]]:
        """Unsubscribe from current channel via multi-tier flow with session memory tracking."""
        try:
            page = await self.ensure_active_page(page_override=page_override)
        except Exception as e:
            return Err(f"Failed to acquire YouTube page: {e}", code="BROWSER_UNAVAILABLE")

        res = await self._session_manager.execute_action("youtube", "unsubscribe", {}, page)
        if res.is_ok:
            data = res.unwrap()
            ch = data.get("channel") or self._session_memory.last_channel
            self._session_memory.last_channel = ch
            self._session_memory.last_action = "unsubscribe"
            self._session_memory.is_subscribed = False
            self._session_memory.last_action_timestamp = time.time()
            data["session_memory"] = {
                "last_channel": ch,
                "last_action": "unsubscribe",
                "is_subscribed": False,
            }
            try:
                from src.agents.task.runtime_state import RuntimeStateManager

                r_state = RuntimeStateManager.get_instance()
                r_state.set_active_browser_context(
                    target_id="youtube",
                    url=getattr(page, "url", ""),
                    title=ch or getattr(page, "title", lambda: "")(),
                    page_type="channel",
                    page_state="unsubscribed",
                )
            except Exception:
                pass
        return res

    async def close(self, page_override: Optional[Any] = None) -> Result[Dict[str, Any]]:
        """Close the YouTube browser tab without closing other tabs or terminating Chrome."""
        runtime = await self._get_runtime()
        if runtime is None:
            return Err("Browser runtime is not available.", code="BROWSER_UNAVAILABLE")

        tracked_tab = self._tab_tracker.find_tab_by_app("youtube")
        if not tracked_tab:
            tracked_tab = self._tab_tracker.find_tab_by_domain("youtube.com")

        target_id = tracked_tab.target_id if tracked_tab else "youtube"

        try:
            if page_override is not None and hasattr(page_override, "close"):
                if not getattr(page_override, "is_closed", lambda: False)():
                    await page_override.close()
            else:
                await runtime.close_tab(target_id=target_id)

            if tracked_tab:
                self._tab_tracker.untrack_tab(tracked_tab.target_id)
            self._sync_extension_runtime(is_playing=False, active_video="", metadata={"closed": True})
            return Ok({
                "action": "close",
                "target_id": target_id,
                "status": "closed",
                "message": "Closed YouTube tab. Other browser tabs remain open.",
            })
        except Exception as e:
            if tracked_tab:
                self._tab_tracker.untrack_tab(tracked_tab.target_id)
            self._sync_extension_runtime(is_playing=False, active_video="", metadata={"closed": True})
            return Ok({
                "action": "close",
                "target_id": target_id,
                "status": "closed",
                "message": f"YouTube tab closed or was already inactive ({e}). Other tabs remain open.",
            })
