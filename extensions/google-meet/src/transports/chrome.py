"""Google Meet plugin module implements chrome behavior."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from ..config import GoogleMeetConfig
from .chrome_browser_proxy import (
    as_browser_tabs,
    call_browser_proxy_on_node,
    read_browser_tab,
    resolve_chrome_node,
)
from .google_meet_platform_adapter import (
    GOOGLE_MEET_PLATFORM_ADAPTER,
    is_talk_back_mode,
)
from .google_meet_platform_constants import GOOGLE_MEET_NODE_COMMAND
from .types import (
    GoogleMeetBrowserCandidateTab,
    GoogleMeetBrowserTab,
    GoogleMeetChromeHealth,
    GoogleMeetManualAction,
    GoogleMeetTranscriptSnapshot,
)

MeetingBrowserRequestCaller = Callable[[dict[str, Any]], Awaitable[Any]]


@dataclass(slots=True)
class MeetingAudioRuntime:
    backend: str
    device_label: str
    input_command: list[str]
    output_command: list[str]


def should_capture_captions(mode: str, full_config: Any = None) -> bool:
    if mode == "transcribe" or full_config is None:
        return True
    transcripts_cfg = getattr(full_config, "transcripts", None)
    if isinstance(transcripts_cfg, dict):
        return transcripts_cfg.get("enabled", True) is not False
    return True


async def prepare_google_meet_audio_runtime(
    *,
    runtime: Any,
    config: GoogleMeetConfig,
    timeout_ms: int,
) -> MeetingAudioRuntime:
    input_cmd = (
        list(config.chrome.audio_input_command_override)
        if config.chrome.audio_input_command_override
        else list(config.chrome.audio_input_command)
    )
    output_cmd = (
        list(config.chrome.audio_output_command_override)
        if config.chrome.audio_output_command_override
        else list(config.chrome.audio_output_command)
    )
    backend = config.chrome.audio_backend
    device_label = "BlackHole 2ch" if backend == "blackhole-2ch" else "PipeWire / PulseAudio"
    return MeetingAudioRuntime(
        backend=backend,
        device_label=device_label,
        input_command=input_cmd,
        output_command=output_cmd,
    )


async def assert_google_meet_audio_available(
    *,
    runtime: Any,
    config: GoogleMeetConfig,
    timeout_ms: int,
) -> None:
    await prepare_google_meet_audio_runtime(runtime=runtime, config=config, timeout_ms=timeout_ms)


def select_reusable_tab(
    tabs: list[GoogleMeetBrowserCandidateTab],
    url: str,
) -> tuple[list[GoogleMeetBrowserCandidateTab], GoogleMeetBrowserCandidateTab | None]:
    matches = [t for t in tabs if GOOGLE_MEET_PLATFORM_ADAPTER.urls.is_recoverable_tab(t, url)]
    account_hint = GOOGLE_MEET_PLATFORM_ADAPTER.urls.account_hint(url)
    preferred = [
        t
        for t in matches
        if GOOGLE_MEET_PLATFORM_ADAPTER.urls.is_preferred_join_url(t.url)
        and (
            not account_hint
            or GOOGLE_MEET_PLATFORM_ADAPTER.urls.account_hint(t.url) == account_hint
        )
    ]
    return matches, preferred[0] if preferred else None


async def prepare_meeting_browser_tab(
    *,
    call_browser: MeetingBrowserRequestCaller,
    allow_microphone: bool,
    meeting_url: str,
    target_id: str,
    timeout_ms: int,
) -> list[str]:
    plan = GOOGLE_MEET_PLATFORM_ADAPTER.browser.permissions(
        allow_microphone=allow_microphone,
        meeting_url=meeting_url,
    )
    if not plan:
        return GOOGLE_MEET_PLATFORM_ADAPTER.browser.permission_notes(
            allow_microphone=allow_microphone
        )
    try:
        result = await call_browser(
            {
                "method": "POST",
                "path": "/permissions/grant",
                "body": {
                    "origin": plan["origin"],
                    "permissions": plan["permissions"],
                    "optionalPermissions": plan.get("optionalPermissions", []),
                    "targetId": target_id,
                    "timeoutMs": min(timeout_ms, 5000),
                },
                "timeoutMs": min(timeout_ms, 5000),
            }
        )
        return GOOGLE_MEET_PLATFORM_ADAPTER.browser.permission_notes(
            allow_microphone=allow_microphone,
            result=result,
        )
    except Exception as error:
        return GOOGLE_MEET_PLATFORM_ADAPTER.browser.permission_notes(
            allow_microphone=allow_microphone,
            error=error,
        )


async def open_meeting_with_browser(
    *,
    call_browser: MeetingBrowserRequestCaller,
    config: Any,
    session: dict[str, Any],
) -> dict[str, Any]:
    if not getattr(config, "launch", True):
        return {"launched": False}

    join_timeout_ms = getattr(config, "join_timeout_ms", 30000)
    timeout_ms = max(1000, join_timeout_ms)
    reuse_tab = getattr(config, "reuse_existing_tab", True)
    url = session.get("url", "")
    mode = session.get("mode", "agent")
    meeting_session_id = session.get("meeting_session_id", "")
    capture_captions = session.get("capture_captions", True)
    auto_join = getattr(config, "auto_join", True)
    guest_name = getattr(config, "guest_name", "")
    wait_for_in_call_ms = getattr(config, "wait_for_in_call_ms", 15000)

    target_id: str | None = None
    tab: GoogleMeetBrowserCandidateTab | None = None
    opened_by_plugin = False

    if reuse_tab:
        try:
            tabs_raw = await call_browser(
                {
                    "method": "GET",
                    "path": "/tabs",
                    "timeoutMs": min(timeout_ms, 5000),
                }
            )
            tabs = as_browser_tabs(tabs_raw)
            reusable_matches, found_tab = select_reusable_tab(tabs, url)
            tab = found_tab
            if not tab and not GOOGLE_MEET_PLATFORM_ADAPTER.urls.account_hint(url):
                for candidate in reusable_matches:
                    if candidate.url:
                        url = candidate.url
                        break
            if tab and tab.target_id:
                target_id = tab.target_id
                await call_browser(
                    {
                        "method": "POST",
                        "path": "/tabs/focus",
                        "body": {"targetId": target_id},
                        "timeoutMs": min(timeout_ms, 5000),
                    }
                )
        except Exception:
            pass

    if not target_id:
        join_url = GOOGLE_MEET_PLATFORM_ADAPTER.urls.build_join_url(url)
        open_res = await call_browser(
            {
                "method": "POST",
                "path": "/tabs/open",
                "body": {"url": join_url},
                "timeoutMs": timeout_ms,
            }
        )
        opened_tab = read_browser_tab(open_res)
        if opened_tab:
            tab = opened_tab
            target_id = opened_tab.target_id
            opened_by_plugin = bool(target_id)

    if not target_id:
        return {
            "launched": True,
            "browser": GoogleMeetChromeHealth(
                notes=["Browser proxy opened Meet but did not return a targetId."],
                browser_url=tab.url if tab else None,
                browser_title=tab.title if tab else None,
            ),
        }

    tab_identity = GoogleMeetBrowserTab(
        target_id=target_id,
        opened_by_plugin=opened_by_plugin,
    )
    allow_mic = GOOGLE_MEET_PLATFORM_ADAPTER.browser.allows_microphone(mode)
    permission_notes = await prepare_meeting_browser_tab(
        call_browser=call_browser,
        allow_microphone=allow_mic,
        meeting_url=url,
        target_id=target_id,
        timeout_ms=timeout_ms,
    )

    deadline = time.time() + (max(0, wait_for_in_call_ms) / 1000.0)
    browser_health: GoogleMeetChromeHealth | None = GoogleMeetChromeHealth(
        browser_url=tab.url if tab else None,
        browser_title=tab.title if tab else None,
        notes=permission_notes if permission_notes else None,
    )
    allow_session_adoption = True

    while True:
        try:
            adopt_session = allow_session_adoption
            allow_session_adoption = False
            action_timeout_ms = min(timeout_ms, 10000)
            script = GOOGLE_MEET_PLATFORM_ADAPTER.browser.build_status_join_script(
                mode=mode,
                auto_join=auto_join,
                capture_captions=capture_captions,
                guest_name=guest_name,
                meeting_session_id=meeting_session_id,
                allow_session_adoption=adopt_session,
                wait_for_in_call_ms=wait_for_in_call_ms,
                url=url,
            )
            evaluated = await call_browser(
                {
                    "method": "POST",
                    "path": "/act",
                    "body": {
                        "kind": "evaluate",
                        "targetId": target_id,
                        "fn": script,
                    },
                    "timeoutMs": action_timeout_ms,
                }
            )
            parsed_health = GOOGLE_MEET_PLATFORM_ADAPTER.browser.parse_status(evaluated)
            if parsed_health:
                if permission_notes:
                    existing_notes = parsed_health.notes or []
                    all_notes = list(dict.fromkeys(existing_notes + permission_notes))
                    parsed_health = GoogleMeetChromeHealth(
                        **{**parsed_health.__dict__, "notes": all_notes}
                    )
                browser_health = parsed_health

            manual: GoogleMeetManualAction | None = None
            if browser_health:
                manual = GOOGLE_MEET_PLATFORM_ADAPTER.browser.classify_manual_action(browser_health)
                if manual:
                    browser_health.manual_action = manual

            should_retry = (
                GOOGLE_MEET_PLATFORM_ADAPTER.browser.should_retry_join_status(browser_health)
                if browser_health
                else False
            )
            if (
                not should_retry
                and browser_health
                and browser_health.in_call is True
                and browser_health.manual_action is None
                and (not allow_mic or browser_health.mic_muted is not True)
            ):
                return {
                    "launched": True,
                    "browser": browser_health,
                    "tab": tab_identity,
                }
            if not should_retry and browser_health and browser_health.manual_action:
                return {
                    "launched": True,
                    "browser": browser_health,
                    "tab": tab_identity,
                }
        except Exception as error:
            manual = GOOGLE_MEET_PLATFORM_ADAPTER.browser.browser_control_unavailable(error)
            notes = list(permission_notes)
            notes.append(f"Browser control could not inspect or auto-join Meet: {error}")
            browser_health = GoogleMeetChromeHealth(
                in_call=False,
                manual_action=manual,
                notes=notes,
            )
            break

        remaining_wait = deadline - time.time()
        if remaining_wait <= 0:
            break
        await asyncio.sleep(min(0.75, remaining_wait))

    return {"launched": True, "browser": browser_health, "tab": tab_identity}


async def recover_meeting_browser_tab(
    *,
    allow_session_adoption: bool = True,
    auto_join: bool = False,
    call_browser: MeetingBrowserRequestCaller,
    capture_captions: bool = True,
    config: Any,
    location_label: str = "in local Chrome",
    meeting_session_id: str = "",
    mode: str = "bidi",
    read_only: bool = False,
    requested_meeting_url: str | None = None,
    timeout_ms: int | None = None,
    tracked_meeting_url: str | None = None,
    tracked_target_id: str | None = None,
) -> dict[str, Any]:
    configured_timeout_ms = max(1000, getattr(config, "join_timeout_ms", 30000))
    resolved_timeout_ms = (
        configured_timeout_ms
        if timeout_ms is None
        else max(1, min(configured_timeout_ms, timeout_ms))
    )
    tabs_raw = await call_browser(
        {
            "method": "GET",
            "path": "/tabs",
            "timeoutMs": min(resolved_timeout_ms, 5000),
        }
    )
    tabs = as_browser_tabs(tabs_raw)

    tracked_candidate = (
        next((t for t in tabs if t.target_id == tracked_target_id), None)
        if tracked_target_id
        else None
    )
    tracked_has_meeting_id = bool(
        GOOGLE_MEET_PLATFORM_ADAPTER.urls.normalize_for_reuse(
            tracked_candidate.url if tracked_candidate else None
        )
    )
    tracked_identity_matches = GOOGLE_MEET_PLATFORM_ADAPTER.urls.is_same_meeting(
        tracked_meeting_url, requested_meeting_url
    )
    tracked_url_matches = GOOGLE_MEET_PLATFORM_ADAPTER.urls.is_same_meeting(
        tracked_candidate.url if tracked_candidate else None,
        requested_meeting_url,
    )
    tracked_tab = (
        tracked_candidate
        if (
            tracked_candidate
            and tracked_identity_matches
            and (not tracked_has_meeting_id or tracked_url_matches)
        )
        else None
    )

    tab: GoogleMeetBrowserCandidateTab | None = None
    if tracked_tab:
        tab = tracked_tab
    else:
        candidates = [
            t
            for t in tabs
            if GOOGLE_MEET_PLATFORM_ADAPTER.urls.is_recoverable_tab(t, requested_meeting_url)
        ]
        if not requested_meeting_url:
            meeting_candidates = [
                t
                for t in candidates
                if GOOGLE_MEET_PLATFORM_ADAPTER.urls.normalize_for_reuse(t.url)
            ]
            preferred = [
                t
                for t in meeting_candidates
                if GOOGLE_MEET_PLATFORM_ADAPTER.urls.is_preferred_join_url(t.url)
            ]
            tab = (
                preferred[0]
                if preferred
                else (
                    meeting_candidates[0]
                    if meeting_candidates
                    else (candidates[0] if candidates else None)
                )
            )
        else:
            account_hint = GOOGLE_MEET_PLATFORM_ADAPTER.urls.account_hint(requested_meeting_url)
            account_candidates = (
                [
                    t
                    for t in candidates
                    if GOOGLE_MEET_PLATFORM_ADAPTER.urls.account_hint(t.url) == account_hint
                ]
                if account_hint
                else candidates
            )
            preferred = [
                t
                for t in account_candidates
                if GOOGLE_MEET_PLATFORM_ADAPTER.urls.is_preferred_join_url(t.url)
            ]
            tab = (
                preferred[0]
                if preferred
                else (account_candidates[0] if account_candidates else None)
            )

    if not tab or not tab.target_id:
        return {
            "found": False,
            "target_id": None,
            "tab": tab,
            "browser": None,
            "message": (
                f"No existing Meet tab matched {requested_meeting_url}."
                if requested_meeting_url
                else f"No existing Meet tab found {location_label}."
            ),
        }

    target_id = tab.target_id
    try:
        await call_browser(
            {
                "method": "POST",
                "path": "/tabs/focus",
                "body": {"targetId": target_id},
                "timeoutMs": min(resolved_timeout_ms, 5000),
            }
        )
    except Exception:
        pass

    locale_act = GOOGLE_MEET_PLATFORM_ADAPTER.urls.locale_action(tab)
    if locale_act:
        return {
            "found": True,
            "target_id": target_id,
            "tab": tab,
            "browser": GoogleMeetChromeHealth(
                browser_url=tab.url,
                browser_title=tab.title,
                manual_action=locale_act,
            ),
            "message": locale_act.message,
        }

    allow_mic = GOOGLE_MEET_PLATFORM_ADAPTER.browser.allows_microphone(mode)
    permission_notes = (
        []
        if read_only
        else await prepare_meeting_browser_tab(
            call_browser=call_browser,
            allow_microphone=allow_mic,
            meeting_url=requested_meeting_url or tab.url or "",
            target_id=target_id,
            timeout_ms=resolved_timeout_ms,
        )
    )

    script = GOOGLE_MEET_PLATFORM_ADAPTER.browser.build_status_join_script(
        allow_session_adoption=allow_session_adoption,
        meeting_session_id=meeting_session_id,
        mode=mode,
        url=requested_meeting_url or tab.url or "",
        auto_join=auto_join,
        capture_captions=capture_captions,
        guest_name=getattr(config, "guest_name", ""),
        read_only=read_only,
        wait_for_in_call_ms=getattr(config, "wait_for_in_call_ms", 15000),
    )

    evaluated = await call_browser(
        {
            "method": "POST",
            "path": "/act",
            "body": {
                "kind": "evaluate",
                "targetId": target_id,
                "fn": script,
            },
            "timeoutMs": min(resolved_timeout_ms, 10000),
        }
    )

    health = GOOGLE_MEET_PLATFORM_ADAPTER.browser.parse_status(evaluated) or GoogleMeetChromeHealth(
        browser_url=tab.url,
        browser_title=tab.title,
    )
    if permission_notes:
        health_notes = health.notes or []
        health = GoogleMeetChromeHealth(
            **{**health.__dict__, "notes": list(dict.fromkeys(health_notes + permission_notes))}
        )

    manual = GOOGLE_MEET_PLATFORM_ADAPTER.browser.classify_manual_action(health)
    if manual:
        health.manual_action = manual

    msg = (
        manual.message
        if manual
        else ("Existing Meet tab is in-call." if health.in_call else "Existing Meet tab focused.")
    )

    return {
        "found": True,
        "target_id": target_id,
        "tab": tab,
        "browser": health,
        "message": msg,
    }


async def leave_meeting_with_browser(
    *,
    call_browser: MeetingBrowserRequestCaller,
    launch: bool,
    meeting_session_id: str = "",
    meeting_url: str,
    tab: GoogleMeetBrowserTab,
    timeout_ms: int,
) -> dict[str, Any]:
    if not launch:
        return {
            "left": False,
            "note": "Browser leave skipped because chrome.launch is disabled.",
        }

    resolved_timeout_ms = min(max(1000, timeout_ms), 5000)
    target_id = tab.target_id
    opened_by_plugin = tab.opened_by_plugin

    tabs_raw = await call_browser(
        {
            "method": "GET",
            "path": "/tabs",
            "timeoutMs": resolved_timeout_ms,
        }
    )
    tabs = as_browser_tabs(tabs_raw)
    current_tab = next((t for t in tabs if t.target_id == target_id), None)
    if not current_tab:
        return {"left": True, "note": "Meet tab is already closed."}

    script = GOOGLE_MEET_PLATFORM_ADAPTER.browser.build_leave_script(meeting_url)
    evaluated = await call_browser(
        {
            "method": "POST",
            "path": "/act",
            "body": {
                "kind": "evaluate",
                "targetId": target_id,
                "fn": script,
            },
            "timeoutMs": resolved_timeout_ms,
        }
    )
    leave_step = GOOGLE_MEET_PLATFORM_ADAPTER.browser.parse_leave_result(evaluated)
    clicked_leave = leave_step.get("leaveAction") == "leave"
    departed = leave_step.get("departed") is True

    tab_closed = False
    if opened_by_plugin:
        try:
            await call_browser(
                {
                    "method": "DELETE",
                    "path": f"/tabs/{target_id}",
                    "timeoutMs": 2000,
                }
            )
            tab_closed = True
        except Exception:
            pass

    if opened_by_plugin:
        note = (
            "Clicked Meet's Leave call button and closed the Meet tab."
            if clicked_leave
            else "Closed the Meet tab to leave the meeting (Leave call button was not found)."
        )
        return {"left": tab_closed or departed, "note": note}

    if departed:
        note = "Clicked Meet's Leave call button; kept the reused browser tab open."
    elif clicked_leave:
        note = (
            "Clicked Meet's Leave call button, but could not verify departure; leave it manually."
        )
    else:
        note = (
            "Could not find Meet's Leave call button in the reused browser tab; leave it manually."
        )

    return {"left": departed, "note": note}


async def read_meeting_transcript_with_browser(
    *,
    call_browser: MeetingBrowserRequestCaller,
    finalize: bool,
    meeting_url: str,
    meeting_session_id: str,
    tab: GoogleMeetBrowserTab,
    timeout_ms: int,
) -> GoogleMeetTranscriptSnapshot:
    script = GOOGLE_MEET_PLATFORM_ADAPTER.browser.captions.build_transcript_script(
        finalize=finalize,
        meeting_session_id=meeting_session_id,
        meeting_url=meeting_url,
    )
    evaluated = await call_browser(
        {
            "method": "POST",
            "path": "/act",
            "body": {
                "kind": "evaluate",
                "targetId": tab.target_id,
                "fn": script,
            },
            "timeoutMs": max(1000, timeout_ms),
        }
    )
    snapshot = GOOGLE_MEET_PLATFORM_ADAPTER.browser.captions.parse_transcript(evaluated)
    if snapshot.url_matched is False:
        raise ValueError("The tracked Meet tab no longer shows this session's meeting URL.")
    if snapshot.session_matched is False:
        raise ValueError("The tracked Meet tab now belongs to another meeting session.")
    return snapshot


async def resolve_local_meeting_browser_request(runtime: Any) -> MeetingBrowserRequestCaller:
    async def call_browser(request: dict[str, Any]) -> Any:
        # Calls browser proxy on local runtime
        browser_service = getattr(runtime, "browser", None)
        if browser_service and hasattr(browser_service, "request"):
            return await browser_service.request(request)
        # Fallback to runtime.nodes or HTTP proxy if registered
        nodes_service = getattr(runtime, "nodes", None)
        if nodes_service and hasattr(nodes_service, "call_browser"):
            return await nodes_service.call_browser(request)
        return {"tabs": []}

    return call_browser


def chrome_node_browser_request(runtime: Any, node_id: str) -> MeetingBrowserRequestCaller:
    async def call_browser(request: dict[str, Any]) -> Any:
        return await call_browser_proxyOn_node(
            runtime=runtime,
            node_id=node_id,
            method=request.get("method", "GET"),
            path=request.get("path", "/tabs"),
            body=request.get("body"),
            timeout_ms=request.get("timeoutMs", 5000),
        )

    return call_browser


async def call_browser_proxyOn_node(
    runtime: Any,
    node_id: str,
    method: str,
    path: str,
    body: Any = None,
    timeout_ms: int = 5000,
) -> Any:
    return await call_browser_proxy_on_node(
        runtime=runtime,
        node_id=node_id,
        method=method,
        path=path,
        body=body,
        timeout_ms=timeout_ms,
    )


async def launch_chrome_meet(
    *,
    runtime: Any,
    config: GoogleMeetConfig,
    full_config: Any = None,
    meeting_session_id: str,
    requester_session_key: str | None = None,
    mode: str,
    url: str,
    logger: Any = None,
) -> dict[str, Any]:
    audio: MeetingAudioRuntime | None = None
    if is_talk_back_mode(mode):
        audio = await prepare_google_meet_audio_runtime(
            runtime=runtime,
            config=config,
            timeout_ms=min(config.chrome.join_timeout_ms, 10000),
        )
        if config.chrome.audio_bridge_health_command:
            system = getattr(runtime, "system", None)
            if system and hasattr(system, "run_command_with_timeout"):
                health = await system.run_command_with_timeout(
                    config.chrome.audio_bridge_health_command,
                    timeout_ms=config.chrome.join_timeout_ms,
                )
                if getattr(health, "code", 0) != 0:
                    raise RuntimeError(
                        f"Chrome audio bridge health check failed: {getattr(health, 'stderr', '') or getattr(health, 'stdout', '')}"
                    )

    call_browser = await resolve_local_meeting_browser_request(runtime)

    if not config.chrome.launch:
        recovered = await recover_meeting_browser_tab(
            allow_session_adoption=True,
            auto_join=config.chrome.auto_join,
            call_browser=call_browser,
            capture_captions=should_capture_captions(mode, full_config),
            config=config.chrome,
            location_label="in local Chrome",
            meeting_session_id=meeting_session_id,
            mode=mode,
            requested_meeting_url=url,
            tracked_meeting_url=url,
            tracked_target_id=None,
        )
        tab_obj = (
            GoogleMeetBrowserTab(
                target_id=recovered["target_id"],
                opened_by_plugin=False,
            )
            if recovered.get("target_id")
            else None
        )
        return {
            "launched": False,
            "audio_backend": audio.backend if audio else None,
            "audio_bridge": None,
            "browser": recovered.get("browser"),
            "tab": tab_obj,
        }

    result = await open_meeting_with_browser(
        call_browser=call_browser,
        config=config.chrome,
        session={
            "capture_captions": should_capture_captions(mode, full_config),
            "meeting_session_id": meeting_session_id,
            "mode": mode,
            "url": url,
        },
    )
    return {
        **result,
        "audio_backend": audio.backend if audio else None,
        "audio_bridge": None,
    }


async def launch_chrome_meet_on_node(
    *,
    runtime: Any,
    config: GoogleMeetConfig,
    full_config: Any = None,
    meeting_session_id: str,
    requester_session_key: str | None = None,
    mode: str,
    url: str,
    logger: Any = None,
) -> dict[str, Any]:
    node_id = await resolve_chrome_node(
        runtime=runtime,
        requested_node=config.chrome_node.node,
    )
    nodes_service = getattr(runtime, "nodes", None)
    if nodes_service and hasattr(nodes_service, "invoke"):
        try:
            await nodes_service.invoke(
                node_id=node_id,
                command=GOOGLE_MEET_NODE_COMMAND,
                params={"action": "stopByUrl", "url": url, "mode": mode},
                timeout_ms=5000,
            )
        except Exception:
            pass

    call_browser = chrome_node_browser_request(runtime, node_id)
    browser_control = await open_meeting_with_browser(
        call_browser=call_browser,
        config=config.chrome,
        session={
            "capture_captions": should_capture_captions(mode, full_config),
            "mode": mode,
            "meeting_session_id": meeting_session_id,
            "url": url,
        },
    )
    return {
        "node_id": node_id,
        "launched": browser_control.get("launched", False),
        "audio_backend": config.chrome.audio_backend,
        "audio_bridge": None,
        "browser": browser_control.get("browser"),
        "tab": browser_control.get("tab"),
    }


async def leave_chrome_meet(
    *,
    runtime: Any,
    config: GoogleMeetConfig,
    meeting_session_id: str,
    meeting_url: str,
    tab: GoogleMeetBrowserTab,
    transport: str = "chrome",
    node_id: str | None = None,
) -> dict[str, Any]:
    resolved_node_id = node_id
    if transport == "chrome-node" and not resolved_node_id:
        resolved_node_id = await resolve_chrome_node(
            runtime=runtime,
            requested_node=config.chrome_node.node,
        )

    call_browser = (
        chrome_node_browser_request(runtime, resolved_node_id)
        if (transport == "chrome-node" and resolved_node_id)
        else await resolve_local_meeting_browser_request(runtime)
    )
    return await leave_meeting_with_browser(
        call_browser=call_browser,
        launch=config.chrome.launch,
        meeting_session_id=meeting_session_id,
        meeting_url=meeting_url,
        tab=tab,
        timeout_ms=config.chrome.join_timeout_ms,
    )


async def read_chrome_meet_transcript(
    *,
    runtime: Any,
    config: GoogleMeetConfig,
    meeting_url: str,
    meeting_session_id: str,
    tab: GoogleMeetBrowserTab,
    transport: str = "chrome",
    node_id: str | None = None,
    finalize: bool = False,
) -> GoogleMeetTranscriptSnapshot:
    resolved_node_id = node_id
    if transport == "chrome-node" and not resolved_node_id:
        resolved_node_id = await resolve_chrome_node(
            runtime=runtime,
            requested_node=config.chrome_node.node,
        )

    call_browser = (
        chrome_node_browser_request(runtime, resolved_node_id)
        if (transport == "chrome-node" and resolved_node_id)
        else await resolve_local_meeting_browser_request(runtime)
    )
    return await read_meeting_transcript_with_browser(
        call_browser=call_browser,
        finalize=finalize,
        meeting_url=meeting_url,
        meeting_session_id=meeting_session_id,
        tab=tab,
        timeout_ms=min(max(1000, config.chrome.join_timeout_ms), 10000),
    )


async def recover_current_meet_tab(
    *,
    runtime: Any,
    config: GoogleMeetConfig,
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
            requested_node=config.chrome_node.node,
        )

    call_browser = (
        chrome_node_browser_request(runtime, node_id)
        if (transport == "chrome-node" and node_id)
        else await resolve_local_meeting_browser_request(runtime)
    )
    recovered = await recover_meeting_browser_tab(
        allow_session_adoption=False,
        auto_join=config.chrome.auto_join,
        call_browser=call_browser,
        capture_captions=should_capture_captions(mode, full_config),
        config=config.chrome,
        location_label=(
            "on the selected Chrome node" if transport == "chrome-node" else "in local Chrome"
        ),
        mode=mode,
        read_only=read_only,
        requested_meeting_url=url,
        tracked_meeting_url=tracked_meeting_url,
        tracked_target_id=tracked_target_id,
    )
    return {
        "transport": transport,
        **({"node_id": node_id} if node_id else {}),
        **recovered,
    }
