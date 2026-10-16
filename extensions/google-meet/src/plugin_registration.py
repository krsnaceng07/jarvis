"""Plugin registration, tool dispatch, and gateway RPC adapters for Google Meet."""

from __future__ import annotations

import sys
from typing import Any, Callable

from .browser_manual_action_error import is_google_meet_browser_manual_action_error
from .config import (
    GoogleMeetConfig,
    resolve_google_meet_gateway_operation_timeout_ms,
)
from .node_invoke_policy import (
    create_google_meet_chrome_node_invoke_policy,
)
from .runtime import GoogleMeetRuntime


def normalize_transport(value: Any) -> str | None:
    if value in ("chrome", "chrome-node", "twilio"):
        return str(value)
    return None


def normalize_mode(value: Any) -> str | None:
    if value == "realtime":
        return "agent"
    if value in ("agent", "bidi", "transcribe"):
        return str(value)
    return None


def resolve_meeting_input(config: GoogleMeetConfig, value: Any) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    if config.defaults.meeting and config.defaults.meeting.strip():
        return config.defaults.meeting.strip()
    raise ValueError("Meeting input is required")


def should_join_created_meet(raw: dict[str, Any]) -> bool:
    join_val = raw.get("join")
    return join_val is not False and join_val != "false"


def google_meet_gateway_method_for_tool_action(action: str) -> str:
    mapping = {
        "recover_current_tab": "googlemeet.recoverCurrentTab",
        "setup_status": "googlemeet.setup",
        "test_speech": "googlemeet.testSpeech",
        "test_listen": "googlemeet.testListen",
        "end_active_conference": "googlemeet.endActiveConference",
    }
    return mapping.get(action, f"googlemeet.{action}")


def is_google_meet_agent_tool_action_unsupported_on_host(
    *,
    config: GoogleMeetConfig,
    raw: dict[str, Any],
    platform: str | None = None,
) -> bool:
    plat = platform or sys.platform
    if plat in ("darwin", "linux"):
        return False
    action = raw.get("action")
    if (
        action != "join"
        and action != "test_speech"
        and not (action == "create" and should_join_created_meet(raw))
    ):
        return False

    transport = normalize_transport(raw.get("transport")) or config.default_transport
    mode = (
        "agent"
        if action == "test_speech"
        else (normalize_mode(raw.get("mode")) or config.default_mode)
    )
    return transport == "chrome" and (mode in ("agent", "bidi"))


def assert_google_meet_agent_tool_action_supported(
    *,
    config: GoogleMeetConfig,
    raw: dict[str, Any],
) -> None:
    if not is_google_meet_agent_tool_action_unsupported_on_host(config=config, raw=raw):
        return
    raise RuntimeError(
        "Google Meet local Chrome talk-back audio requires macOS with BlackHole 2ch or Linux with PipeWire-Pulse. On this host, use mode: transcribe, transport: twilio, or a supported chrome-node."
    )


async def call_google_meet_gateway_from_tool(
    *,
    config: GoogleMeetConfig,
    action: str,
    raw: dict[str, Any],
    runtime: Any = None,
) -> Any:
    timeout_ms = resolve_google_meet_gateway_operation_timeout_ms(config)
    method = google_meet_gateway_method_for_tool_action(action)
    if runtime:
        gateway = getattr(runtime, "gateway", None)
        if gateway and hasattr(gateway, "request"):
            return await gateway.request(method, raw, timeout_ms=timeout_ms)
    return {"ok": True, "action": action}


def keep_trusted_tool_agent_id(
    raw: dict[str, Any],
    client: Any = None,
) -> dict[str, Any]:
    internal_owner = None
    if client and isinstance(getattr(client, "internal", None), dict):
        internal_owner = client.internal.get("pluginRuntimeOwnerId")
    if internal_owner != "google-meet":
        return {k: v for k, v in raw.items() if k != "agentId"}
    return dict(raw)


def create_google_meet_runtime_accessor(
    *,
    api: Any,
    config: GoogleMeetConfig,
) -> Callable[[], Any]:
    runtime_instance: GoogleMeetRuntime | None = None

    async def ensure_runtime() -> GoogleMeetRuntime:
        nonlocal runtime_instance
        if not config.enabled:
            raise RuntimeError("Google Meet plugin disabled in plugin config")
        if runtime_instance is None:
            runtime_instance = GoogleMeetRuntime(
                config=config,
                full_config=getattr(api, "config", None),
                runtime=getattr(api, "runtime", None),
                logger=getattr(api, "logger", None),
            )
        return runtime_instance

    return ensure_runtime


def create_lazy_google_meet_node_invoke_policy(
    config: GoogleMeetConfig,
) -> Any:
    return create_google_meet_chrome_node_invoke_policy(config)


def format_google_meet_gateway_error(err: Any) -> dict[str, Any]:
    if is_google_meet_browser_manual_action_error(err):
        return getattr(err, "payload", {"error": str(err)})
    return {"error": str(err)}


def send_google_meet_gateway_error(
    respond: Callable[..., None],
    err: Any,
    code: str = "UNAVAILABLE",
) -> None:
    payload = format_google_meet_gateway_error(err)
    message = (
        payload.get("error")
        if isinstance(payload.get("error"), str)
        else "Google Meet request failed"
    )
    respond(False, None, {"code": code, "message": message, **payload})


GOOGLE_MEET_GATEWAY_METHOD_SPECS = [
    {"method": "googlemeet.space.create", "description": "Create a new Google Meet space."},
    {"method": "googlemeet.space.resolve", "description": "Resolve space metadata."},
    {"method": "googlemeet.space.endActiveConference", "description": "End active conference."},
    {"method": "googlemeet.space.preflight", "description": "Preflight health check."},
    {
        "method": "googlemeet.calendar.listEvents",
        "description": "List calendar events with Meet links.",
    },
    {"method": "googlemeet.artifacts.get", "description": "Get meeting artifacts."},
    {"method": "googlemeet.attendance.get", "description": "Get meeting attendance summary."},
    {"method": "googlemeet.export.bundle", "description": "Export meeting bundle."},
    {"method": "googlemeet.session.join", "description": "Join meeting session."},
    {"method": "googlemeet.session.leave", "description": "Leave meeting session."},
    {"method": "googlemeet.session.speak", "description": "Speak in meeting session."},
    {"method": "googlemeet.session.status", "description": "Get meeting session status."},
    {"method": "googlemeet.session.transcript", "description": "Get realtime transcript."},
    {"method": "googlemeet.session.recoverTab", "description": "Recover Chrome tab."},
    {"method": "googlemeet.probes.testSpeech", "description": "Test speech playback probe."},
    {"method": "googlemeet.probes.testListen", "description": "Test microphone listening probe."},
]


async def handle_google_meet_gateway_rpc(
    *,
    method: str,
    params: dict[str, Any],
    raw_config: dict[str, Any],
    runtime: Any = None,
) -> dict[str, Any]:
    """Dispatch Gateway RPC calls to Google Meet tool actions and runtime."""
    from .plugin_helpers import execute_google_meet_action

    method_to_action = {
        "googlemeet.space.create": "create",
        "googlemeet.space.resolve": "resolve-space",
        "googlemeet.space.endActiveConference": "end-active-conference",
        "googlemeet.space.preflight": "preflight",
        "googlemeet.calendar.listEvents": "calendar-events",
        "googlemeet.artifacts.get": "artifacts",
        "googlemeet.attendance.get": "attendance",
        "googlemeet.export.bundle": "export",
        "googlemeet.session.join": "join",
        "googlemeet.session.leave": "leave",
        "googlemeet.session.speak": "speak",
        "googlemeet.session.status": "status",
        "googlemeet.session.transcript": "transcript",
        "googlemeet.session.recoverTab": "recover-tab",
        "googlemeet.probes.testSpeech": "test-speech",
        "googlemeet.probes.testListen": "test-listen",
    }

    action = method_to_action.get(method)
    if not action:
        return {"error": f"Unsupported Google Meet gateway method: {method}"}

    return await execute_google_meet_action(
        action_name=action,
        params=params,
        raw_config=raw_config,
        runtime=runtime,
    )
