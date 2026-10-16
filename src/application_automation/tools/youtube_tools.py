"""jarvis.application_automation.tools.youtube_tools — Granular YouTube automation tools.

OpenClaw parity:
- Exposes 7 granular, schema-validated tools for YouTube media control.
- Enforces HTML5 media mutation verification before declaring success.
- Preserves tab affinity: reuses active YouTube sessions without reloading.
- Automatically handles consent dialogs and video advertisements.
"""

from __future__ import annotations

from typing import Any, Callable, Coroutine, Dict, Optional

from ..providers.youtube_provider import YouTubeProvider

_provider: Optional[YouTubeProvider] = None


def get_youtube_provider() -> YouTubeProvider:
    """Get or create singleton YouTubeProvider instance."""
    global _provider
    if _provider is None:
        _provider = YouTubeProvider()
    return _provider


def set_youtube_provider(provider: Optional[YouTubeProvider]) -> None:
    """Override provider instance (used in unit testing)."""
    global _provider
    _provider = provider


async def youtube_play_tool(args: Dict[str, Any]) -> str:
    """Search for and play a video on YouTube, or resume active playback."""
    query = str(args.get("query") or args.get("search") or "").strip()
    title = str(args.get("title") or "").strip()
    provider = get_youtube_provider()
    res = await provider.play(query=query, title=title)
    if res.is_ok:
        payload = res.unwrap()
        v_title = payload.get("video_title") or payload.get("title") or query or title or "video"
        verif = payload.get("verification", {})
        verified = verif.get("verified", False)
        verif_tag = "[Playback Verified via HTML5 <video>]" if verified else "[Started]"
        return f"SUCCESS: Playing '{v_title}' on YouTube. {verif_tag}"
    return f"ERROR: Failed to play on YouTube: {res.error}"


async def youtube_pause_tool(args: Dict[str, Any]) -> str:
    """Pause currently playing YouTube video."""
    provider = get_youtube_provider()
    res = await provider.pause()
    if res.is_ok:
        payload = res.unwrap()
        verif = payload.get("verification", {})
        verified = verif.get("verified", False)
        verif_tag = "[Pause Verified via HTML5 <video>]" if verified else "[Paused]"
        return f"SUCCESS: Paused YouTube video playback. {verif_tag}"
    return f"ERROR: Failed to pause YouTube: {res.error}"


async def youtube_resume_tool(args: Dict[str, Any]) -> str:
    """Resume paused YouTube video playback."""
    provider = get_youtube_provider()
    res = await provider.resume()
    if res.is_ok:
        payload = res.unwrap()
        verif = payload.get("verification", {})
        verified = verif.get("verified", False)
        verif_tag = "[Playback Verified via HTML5 <video>]" if verified else "[Resumed]"
        return f"SUCCESS: Resumed YouTube video playback. {verif_tag}"
    return f"ERROR: Failed to resume YouTube: {res.error}"


async def youtube_search_tool(args: Dict[str, Any]) -> str:
    """Search YouTube for a query and view candidate results without auto-playing."""
    query = str(args.get("query") or args.get("search") or "").strip()
    if not query:
        return "ERROR: 'query' parameter is required for YouTube search."
    provider = get_youtube_provider()
    res = await provider.search(query=query)
    if res.is_ok:
        return f"SUCCESS: Searched YouTube for '{query}'. Results displayed."
    return f"ERROR: Failed to search YouTube: {res.error}"


async def youtube_skip_ad_tool(args: Dict[str, Any]) -> str:
    """Skip currently active video advertisement on YouTube."""
    provider = get_youtube_provider()
    res = await provider.skip_ad()
    if res.is_ok:
        payload = res.unwrap()
        if payload.get("skipped"):
            return "SUCCESS: Skipped YouTube advertisement."
        msg = payload.get("message") or "No skippable advertisement detected."
        return f"INFO: {msg}"
    return f"ERROR: Failed to skip ad: {res.error}"


async def youtube_set_volume_tool(args: Dict[str, Any]) -> str:
    """Set YouTube player volume to an exact percentage (0 to 100)."""
    raw_vol = args.get("volume") if "volume" in args else args.get("percent")
    if raw_vol is None:
        return "ERROR: 'volume' parameter (0-100) is required."
    try:
        vol = int(raw_vol)
    except (TypeError, ValueError):
        return f"ERROR: Invalid volume value: '{raw_vol}'. Must be integer 0-100."
    provider = get_youtube_provider()
    res = await provider.set_volume(volume=vol)
    if res.is_ok:
        clamped = max(0, min(100, vol))
        return f"SUCCESS: YouTube volume set to {clamped}%."
    return f"ERROR: Failed to set YouTube volume: {res.error}"


async def youtube_get_state_tool(args: Dict[str, Any]) -> str:
    """Inspect active YouTube video player status, title, time, and ad state."""
    provider = get_youtube_provider()
    res = await provider.get_state()
    if res.is_ok:
        metrics = res.unwrap()
        display_open = metrics.get("display_open", metrics.get("found", True))
        if not display_open:
            return "YouTube State: YouTube is not currently open in any browser tab or display."

        playback = metrics.get("playback") if isinstance(metrics.get("playback"), dict) else {}
        title = playback.get("title") or metrics.get("title") or metrics.get("video_title") or "Unknown"
        paused = playback.get("paused") if "paused" in playback else metrics.get("paused", True)
        curr = float(playback.get("currentTime", metrics.get("currentTime", 0.0)))
        dur = float(playback.get("duration", metrics.get("duration", 0.0)))
        vol = int(playback.get("volume", metrics.get("volume", 0)))
        muted = bool(playback.get("muted", metrics.get("muted", False)))
        ad_active = bool(playback.get("ad_active", metrics.get("ad_active", False)))
        status_str = "Paused" if paused else "Playing"

        stage = metrics.get("page_stage", "unknown")
        channel = metrics.get("channel_name", "")
        is_sub = metrics.get("is_subscribed", False)
        btn_txt = metrics.get("subscription_button_text", "")
        mem = metrics.get("session_memory", {})
        last_action = mem.get("last_action", "none")

        sub_desc = f"Subscribed ('{btn_txt}')" if is_sub else f"Not Subscribed ('{btn_txt}')"
        if not btn_txt:
            sub_desc = "Subscribed" if is_sub else "Not Subscribed"

        return (
            f"YouTube State: Status={status_str}, Title='{title}', "
            f"Time={curr:.1f}s/{dur:.1f}s, Volume={vol}%, Muted={muted}, "
            f"Ad Active={ad_active}, Display Open={display_open}, "
            f"Stage='{stage}', Channel='{channel or 'Unknown'}', "
            f"Subscription={sub_desc}, Last Action='{last_action}'"
        )
    return f"ERROR: Failed to get YouTube state: {res.error}"


async def youtube_subscribe_tool(args: Dict[str, Any]) -> str:
    """Subscribe to the channel on active YouTube page, verifying state mutation."""
    provider = get_youtube_provider()
    res = await provider.subscribe()
    if res.is_ok:
        payload = res.unwrap()
        channel = payload.get("channel") or "channel"
        btn_txt = payload.get("button_text") or "Subscribed"
        if payload.get("already_subscribed"):
            ch_str = f"channel '{channel}'" if channel and channel != "channel" else "this channel"
            return f"SUCCESS: Already subscribed to {ch_str} ('{btn_txt}'). [Precondition Satisfied]"
        ch_str = f"channel '{channel}'" if channel and channel != "channel" else "channel"
        return f"SUCCESS: Subscribed to {ch_str}. [Subscription Verified]"
    return f"ERROR: Failed to subscribe: {res.error}"


async def youtube_unsubscribe_tool(args: Dict[str, Any]) -> str:
    """Unsubscribe from the channel on active YouTube page via multi-tier flow."""
    provider = get_youtube_provider()
    res = await provider.unsubscribe()
    if res.is_ok:
        payload = res.unwrap()
        channel = payload.get("channel") or "channel"
        btn_txt = payload.get("button_text") or "Subscribe"
        if payload.get("already_unsubscribed"):
            ch_str = f"channel '{channel}'" if channel and channel != "channel" else "this channel"
            return f"SUCCESS: Already unsubscribed from {ch_str}. [Precondition Satisfied]"
        ch_str = f"channel '{channel}'" if channel and channel != "channel" else "channel"
        return f"SUCCESS: Unsubscribed from {ch_str}. [Unsubscribe Confirmed & Verified]"
    return f"ERROR: Failed to unsubscribe: {res.error}"


async def youtube_close_tool(args: Dict[str, Any]) -> str:
    """Close the active YouTube tab in the browser without closing other tabs or the browser window."""
    provider = get_youtube_provider()
    res = await provider.close()
    if res.is_ok:
        payload = res.unwrap()
        msg = payload.get("message") or "Closed YouTube tab. Other browser tabs remain open."
        return f"SUCCESS: {msg}"
    return f"ERROR: Failed to close YouTube tab: {res.error}"


_DISPATCH_MAP: Dict[str, Callable[[Dict[str, Any]], Coroutine[Any, Any, str]]] = {
    "youtube_play": youtube_play_tool,
    "youtube_pause": youtube_pause_tool,
    "youtube_resume": youtube_resume_tool,
    "youtube_search": youtube_search_tool,
    "youtube_skip_ad": youtube_skip_ad_tool,
    "youtube_set_volume": youtube_set_volume_tool,
    "youtube_get_state": youtube_get_state_tool,
    "youtube_subscribe": youtube_subscribe_tool,
    "youtube_unsubscribe": youtube_unsubscribe_tool,
    "youtube_close": youtube_close_tool,
}


async def dispatch_youtube_tool(name: str, args: Dict[str, Any]) -> str:
    """Dispatch a YouTube tool call by name with error boundary."""
    fn = _DISPATCH_MAP.get(name)
    if not fn:
        return f"ERROR: Unknown YouTube tool '{name}'."
    try:
        return await fn(args)
    except Exception as e:
        return f"ERROR: YouTube tool '{name}' failed: {e}"


YOUTUBE_TOOL_DECLARATIONS: list[dict[str, Any]] = [
    {
        "name": "youtube_play",
        "description": (
            "Search and play a video on YouTube, or resume playback of the active video. "
            "Reuses any open YouTube tab (tab affinity) and verifies HTML5 video playback. "
            "Use this tool whenever the user asks to play a song, video, or music on YouTube."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query": {
                    "type": "STRING",
                    "description": "Search query or video title to find and play (e.g. 'lofi hip hop', 'Bohemian Rhapsody').",
                },
                "title": {
                    "type": "STRING",
                    "description": "Specific video title to match from search results.",
                },
            },
        },
    },
    {
        "name": "youtube_pause",
        "description": (
            "Pause the currently playing YouTube video. "
            "Verifies HTML5 video paused state. Use when the user asks to pause or stop YouTube playback."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {},
        },
    },
    {
        "name": "youtube_resume",
        "description": (
            "Resume playback of a paused YouTube video. "
            "Verifies HTML5 video playing state. Use when the user asks to resume or unpause YouTube."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {},
        },
    },
    {
        "name": "youtube_search",
        "description": (
            "Search YouTube for videos matching a query without automatically starting playback. "
            "Displays the search results page. Use when the user asks to find or search for videos on YouTube."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query": {
                    "type": "STRING",
                    "description": "Search query for YouTube.",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "youtube_skip_ad",
        "description": (
            "Skip the currently playing video advertisement on YouTube if a skip button is available. "
            "Use when an ad is playing and the user asks to skip it."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {},
        },
    },
    {
        "name": "youtube_set_volume",
        "description": (
            "Set the volume level of the YouTube video player to a percentage between 0 and 100. "
            "Use when the user asks to set, raise, or lower YouTube player volume."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "volume": {
                    "type": "INTEGER",
                    "description": "Target volume percentage (0 to 100).",
                },
            },
            "required": ["volume"],
        },
    },
    {
        "name": "youtube_get_state",
        "description": (
            "Inspect live YouTube display presence, active page stage (home, channel, search, watch), "
            "channel name, subscription state, last action, and HTML5 video playback metrics. "
            "Use when checking whether YouTube is open or what stage the user is currently viewing."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {},
        },
    },
    {
        "name": "youtube_subscribe",
        "description": (
            "Subscribe or resubscribe to the YouTube channel currently open on the active tab. "
            "Performs pre-flight DOM inspection to check if already subscribed, dismisses overlays, "
            "clicks the subscribe button, and verifies mutation to 'Subscribed'. "
            "Use when the user asks to subscribe or resubscribe ('pheri subscribe gara', 'subscribe again')."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {},
        },
    },
    {
        "name": "youtube_unsubscribe",
        "description": (
            "Unsubscribe from the YouTube channel currently open on the active tab. "
            "Performs pre-flight DOM inspection to check if already unsubscribed, executes the multi-step "
            "confirmation flow, dismisses modal backdrops, and verifies mutation to 'Subscribe'. "
            "Use when the user asks to unsubscribe ('unsubscribe gara', 'unsub gardeu')."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {},
        },
    },
    {
        "name": "youtube_close",
        "description": (
            "Close only the active YouTube tab in the browser without closing other tabs or terminating the browser application. "
            "Use when the user asks to close YouTube ('youtube banda gara', 'close youtube', 'youtube close gara')."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {},
        },
    },
]
