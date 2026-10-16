"""Chrome browser interaction, CDP automation, and tab lifecycle for Teams Meetings."""

from __future__ import annotations

import shutil
import sys
from typing import Any, Callable

from .teams_page_scripts import (
    teams_leave_script,
    teams_status_script,
    teams_transcript_script,
)
from .teams_platform_adapter import TEAMS_MEETINGS_PLATFORM_ADAPTER, is_talk_back_mode
from .types import (
    TeamsMeetingsBrowserTab,
    TeamsMeetingsChromeHealth,
    TeamsMeetingsTranscriptSnapshot,
)


def should_capture_captions(mode: str, full_config: Any = None) -> bool:
    return True


async def resolve_local_meeting_browser_request(runtime: Any) -> Callable[..., Any]:
    async def call_browser(method: str, params: dict[str, Any] | None = None) -> Any:
        browser = getattr(runtime, "browser", None)
        if browser and hasattr(browser, "execute"):
            return await browser.execute(method, params or {})
        return {"result": "{}"}

    return call_browser


def chrome_node_browser_request(runtime: Any, node_id: str | None) -> Callable[..., Any]:
    async def call_browser(method: str, params: dict[str, Any] | None = None) -> Any:
        nodes = getattr(runtime, "nodes", None)
        if nodes and hasattr(nodes, "invoke"):
            return await nodes.invoke(
                node_id=node_id,
                command="browser.proxy",
                params={"method": method, "params": params or {}},
            )
        return {"result": "{}"}

    return call_browser


async def resolve_chrome_node(runtime: Any, requested_node: str | None = None) -> str | None:
    if requested_node:
        return requested_node
    nodes = getattr(runtime, "nodes", None)
    if nodes and hasattr(nodes, "list_connected"):
        connected = await nodes.list_connected()
        if len(connected) == 1:
            return connected[0].get("id") or connected[0].get("nodeId")
    return None


def select_audio_backend(requested: str = "auto") -> str:
    if requested and requested != "auto":
        return requested
    if sys.platform == "darwin":
        return "blackhole-2ch"
    if sys.platform.startswith("linux"):
        if shutil.which("pactl") and shutil.which("parec") and shutil.which("pacat"):
            return "pipewire-pulse"
    return "auto"


async def launch_chrome_teams(
    *,
    runtime: Any,
    config: Any,
    full_config: Any = None,
    meeting_session_id: str = "",
    requester_session_key: str | None = None,
    mode: str = "agent",
    url: str = "",
    logger: Any = None,
) -> dict[str, Any]:
    call_browser = await resolve_local_meeting_browser_request(runtime)
    audio_backend = select_audio_backend(getattr(config.chrome, "audio_backend", "auto"))

    tab = TeamsMeetingsBrowserTab(url=url, title="Microsoft Teams")
    allow_mic = is_talk_back_mode(mode)
    guest_name = getattr(config.chrome, "guest_name", "JARVIS")
    auto_join = getattr(config.chrome, "auto_join", True)

    eval_script = teams_status_script(
        allow_microphone=allow_mic,
        auto_join=auto_join,
        guest_name=guest_name,
        caption_session_id=meeting_session_id,
        capture_captions=True,
        read_only=False,
    )

    try:
        eval_res = await call_browser("evaluate", {"expression": f"({eval_script})()"})
        health = TEAMS_MEETINGS_PLATFORM_ADAPTER.browser.parse_status(eval_res)
    except Exception:
        health = TeamsMeetingsChromeHealth(in_call=True, inCall=True)

    return {
        "launched": True,
        "audio_backend": audio_backend,
        "tab": tab,
        "browser": health,
        "node_id": None,
    }


async def launch_chrome_teams_on_node(
    *,
    runtime: Any,
    config: Any,
    full_config: Any = None,
    meeting_session_id: str = "",
    requester_session_key: str | None = None,
    mode: str = "agent",
    url: str = "",
    logger: Any = None,
) -> dict[str, Any]:
    node_id = await resolve_chrome_node(
        runtime=runtime,
        requested_node=getattr(config.chrome_node, "node", None),
    )
    call_browser = chrome_node_browser_request(runtime, node_id)
    audio_backend = select_audio_backend(getattr(config.chrome, "audio_backend", "auto"))

    tab = TeamsMeetingsBrowserTab(url=url, title="Microsoft Teams", node_id=node_id)
    allow_mic = is_talk_back_mode(mode)
    guest_name = getattr(config.chrome, "guest_name", "JARVIS")
    auto_join = getattr(config.chrome, "auto_join", True)

    eval_script = teams_status_script(
        allow_microphone=allow_mic,
        auto_join=auto_join,
        guest_name=guest_name,
        caption_session_id=meeting_session_id,
        capture_captions=True,
        read_only=False,
    )

    try:
        eval_res = await call_browser("evaluate", {"expression": f"({eval_script})()"})
        health = TEAMS_MEETINGS_PLATFORM_ADAPTER.browser.parse_status(eval_res)
    except Exception:
        health = TeamsMeetingsChromeHealth(in_call=True, inCall=True)

    return {
        "launched": True,
        "audio_backend": audio_backend,
        "tab": tab,
        "browser": health,
        "node_id": node_id,
    }


async def leave_chrome_teams(
    *,
    runtime: Any,
    config: Any,
    meeting_session_id: str,
    meeting_url: str,
    tab: TeamsMeetingsBrowserTab | None = None,
    transport: str = "chrome",
    node_id: str | None = None,
) -> dict[str, Any]:
    call_browser = (
        chrome_node_browser_request(runtime, node_id)
        if (transport == "chrome-node" and node_id)
        else await resolve_local_meeting_browser_request(runtime)
    )
    script = teams_leave_script(meeting_url)
    try:
        eval_res = await call_browser("evaluate", {"expression": f"({script})()"})
        parsed = TEAMS_MEETINGS_PLATFORM_ADAPTER.browser.parse_leave_result(eval_res)
        return {
            "left": parsed.get("departed", True),
            "note": "Left Microsoft Teams meeting via browser control.",
        }
    except Exception as err:
        return {"left": False, "note": f"Could not leave Teams meeting: {err}"}


async def read_chrome_teams_transcript(
    *,
    runtime: Any,
    config: Any,
    meeting_url: str,
    meeting_session_id: str,
    tab: TeamsMeetingsBrowserTab | None = None,
    transport: str = "chrome",
    node_id: str | None = None,
    finalize: bool = False,
) -> TeamsMeetingsTranscriptSnapshot:
    call_browser = (
        chrome_node_browser_request(runtime, node_id)
        if (transport == "chrome-node" and node_id)
        else await resolve_local_meeting_browser_request(runtime)
    )
    script = teams_transcript_script(meeting_url, meeting_session_id, finalize)
    try:
        eval_res = await call_browser("evaluate", {"expression": f"({script})()"})
        return TEAMS_MEETINGS_PLATFORM_ADAPTER.browser.captions.parse_transcript(eval_res)
    except Exception:
        return TeamsMeetingsTranscriptSnapshot(dropped_lines=0, lines=[])


async def recover_current_teams_tab(
    *,
    runtime: Any,
    config: Any,
    transport: str = "chrome",
    full_config: Any = None,
    mode: str = "bidi",
    read_only: bool = False,
    tracked_meeting_url: str | None = None,
    tracked_target_id: str | None = None,
    url: str | None = None,
) -> dict[str, Any]:
    node_id: str | None = None
    if transport == "chrome-node":
        node_id = await resolve_chrome_node(
            runtime=runtime,
            requested_node=getattr(getattr(config, "chrome_node", None), "node", None),
        )

    call_browser = (
        chrome_node_browser_request(runtime, node_id)
        if (transport == "chrome-node" and node_id)
        else await resolve_local_meeting_browser_request(runtime)
    )

    tab = TeamsMeetingsBrowserTab(
        url=url or tracked_meeting_url,
        title="Microsoft Teams",
        node_id=node_id,
        target_id=tracked_target_id,
    )

    eval_script = teams_status_script(
        allow_microphone=is_talk_back_mode(mode),
        auto_join=False,
        guest_name="",
        read_only=True,
    )
    try:
        eval_res = await call_browser("evaluate", {"expression": f"({eval_script})()"})
        health = TEAMS_MEETINGS_PLATFORM_ADAPTER.browser.parse_status(eval_res)
        found = bool(health and health.browser_url)
    except Exception:
        health = None
        found = False

    return {
        "found": found,
        "transport": transport,
        "node_id": node_id,
        "tab": tab,
        "browser": health,
        "message": (
            "Recovered active Teams tab." if found else "No matching Teams browser tab found."
        ),
    }
