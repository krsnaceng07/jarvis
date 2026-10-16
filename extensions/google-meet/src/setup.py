"""Google Meet setup module handles plugin onboarding behavior."""

from __future__ import annotations

import ipaddress
import os
import pathlib
import urllib.parse
from dataclasses import dataclass, field
from typing import Any

from .config import GoogleMeetConfig
from .transports.google_meet_platform_adapter import is_talk_back_mode


@dataclass(slots=True)
class SetupCheck:
    id: str
    ok: bool
    message: str


@dataclass(slots=True)
class GoogleMeetSetupStatus:
    ok: bool
    checks: list[SetupCheck] = field(default_factory=list)


def resolve_user_path(input_path: str) -> str:
    if input_path == "~":
        return str(pathlib.Path.home())
    if input_path.startswith("~/") or input_path.startswith("~\\"):
        return str(pathlib.Path.home() / input_path[2:])
    return input_path


def is_provider_unreachable_webhook_url(webhook_url: str) -> bool:
    try:
        parsed = urllib.parse.urlparse(webhook_url)
        hostname = (parsed.hostname or "").strip().lower()
        if not hostname:
            return True
        if hostname in ("localhost", "localhost.localdomain", "0.0.0.0", "::") or hostname.endswith(
            ".localhost"
        ):
            return True
        try:
            ip = ipaddress.ip_address(hostname)
            return bool(
                ip.is_private
                or ip.is_loopback
                or ip.is_unspecified
                or ip.is_link_local
                or ip.is_reserved
            )
        except ValueError:
            return False
    except Exception:
        return True


def get_voice_call_webhook_exposure_check(voice_call_config: dict[str, Any]) -> SetupCheck:
    public_url = str(voice_call_config.get("publicUrl", "")).strip()
    tunnel = (
        voice_call_config.get("tunnel") if isinstance(voice_call_config.get("tunnel"), dict) else {}
    )
    tailscale = (
        voice_call_config.get("tailscale")
        if isinstance(voice_call_config.get("tailscale"), dict)
        else {}
    )
    tunnel_provider = str(tunnel.get("provider", "")).strip()
    tailscale_mode = str(tailscale.get("mode", "")).strip()

    if public_url:
        ok = not is_provider_unreachable_webhook_url(public_url)
        return SetupCheck(
            id="twilio-voice-call-webhook",
            ok=ok,
            message=(
                f"Voice-call public webhook URL configured: {public_url}"
                if ok
                else f"Voice-call publicUrl is local/private and cannot be reached by Twilio: {public_url}"
            ),
        )

    if tunnel_provider and tunnel_provider != "none":
        return SetupCheck(
            id="twilio-voice-call-webhook",
            ok=True,
            message="Voice-call webhook exposure configured through tunnel",
        )

    if tailscale_mode and tailscale_mode != "off":
        return SetupCheck(
            id="twilio-voice-call-webhook",
            ok=True,
            message="Voice-call webhook exposure configured through Tailscale",
        )

    return SetupCheck(
        id="twilio-voice-call-webhook",
        ok=False,
        message="Set plugins.entries.voice-call.config.publicUrl or configure voice-call tunnel/tailscale exposure for Twilio dialing",
    )


def get_google_meet_setup_status(
    config: GoogleMeetConfig,
    *,
    env: dict[str, str] | None = None,
    full_config: Any = None,
    mode: str | None = None,
    transport: str | None = None,
    twilio_dial_in_number: str | None = None,
) -> GoogleMeetSetupStatus:
    checks: list[SetupCheck] = []
    environ = env if env is not None else dict(os.environ)
    resolved_mode = mode or config.default_mode
    resolved_transport = transport or config.default_transport
    needs_chrome_realtime_audio = is_talk_back_mode(resolved_mode) and (
        resolved_transport in ("chrome", "chrome-node")
    )

    plugins_raw = getattr(full_config, "plugins", {}) if full_config else {}
    plugins_dict = plugins_raw if isinstance(plugins_raw, dict) else {}
    plugin_entries = (
        plugins_dict.get("entries", {}) if isinstance(plugins_dict.get("entries"), dict) else {}
    )
    voice_call_entry = (
        plugin_entries.get("voice-call", {})
        if isinstance(plugin_entries.get("voice-call"), dict)
        else {}
    )
    voice_call_config = (
        voice_call_entry.get("config", {})
        if isinstance(voice_call_entry.get("config"), dict)
        else {}
    )
    voice_call_twilio_config = (
        voice_call_config.get("twilio", {})
        if isinstance(voice_call_config.get("twilio"), dict)
        else {}
    )

    if config.auth.token_path:
        token_path = resolve_user_path(config.auth.token_path)
        exists = os.path.exists(token_path)
        checks.append(
            SetupCheck(
                id="google-oauth-token",
                ok=exists,
                message=(
                    "Google OAuth token file found"
                    if exists
                    else f"Google OAuth token file missing at {config.auth.token_path}"
                ),
            )
        )
    else:
        checks.append(
            SetupCheck(
                id="google-oauth-token",
                ok=True,
                message="Google OAuth token path not configured; Chrome profile auth will be used",
            )
        )

    checks.append(
        SetupCheck(
            id="chrome-profile",
            ok=True,
            message=(
                "Local Chrome uses the JARVIS browser profile; chrome.browserProfile is passed to chrome-node hosts"
                if config.chrome.browser_profile
                else "Local Chrome uses the JARVIS browser profile; configure browser.defaultProfile to choose another profile"
            ),
        )
    )

    if needs_chrome_realtime_audio:
        has_command_pair = bool(
            config.chrome.audio_input_command and config.chrome.audio_output_command
        )
        has_external_bridge = bool(config.chrome.audio_bridge_command)
        agent_mode_external_bridge_invalid = resolved_mode == "agent" and has_external_bridge
        is_ok = (
            (has_command_pair and not agent_mode_external_bridge_invalid)
            if resolved_mode == "agent"
            else (has_external_bridge or has_command_pair)
        )
        msg = (
            "Chrome agent mode requires chrome.audioInputCommand and chrome.audioOutputCommand; chrome.audioBridgeCommand is bidi-only"
            if agent_mode_external_bridge_invalid
            else (
                "Chrome audio bridge command configured"
                if has_external_bridge
                else (
                    f"Chrome command-pair talk-back audio bridge configured ({config.chrome.audio_format})"
                    if has_command_pair
                    else "Chrome talk-back audio bridge not configured"
                )
            )
        )
        checks.append(SetupCheck(id="audio-bridge", ok=is_ok, message=msg))
    elif resolved_transport in ("chrome", "chrome-node"):
        checks.append(
            SetupCheck(
                id="audio-bridge",
                ok=True,
                message="Chrome observe-only mode does not require a realtime audio bridge",
            )
        )

    guest_ok = bool(
        config.chrome.guest_name and config.chrome.auto_join and config.chrome.reuse_existing_tab
    )
    checks.append(
        SetupCheck(
            id="guest-join-defaults",
            ok=guest_ok,
            message=(
                "Guest auto-join and tab reuse defaults are enabled"
                if guest_ok
                else "Set chrome.guestName, chrome.autoJoin, and chrome.reuseExistingTab for unattended guest joins"
            ),
        )
    )

    node_ok = config.default_transport != "chrome-node" or bool(config.chrome_node.node)
    checks.append(
        SetupCheck(
            id="chrome-node-target",
            ok=node_ok,
            message=(
                "chrome-node default should pin chromeNode.node when multiple nodes may be connected"
                if (config.default_transport == "chrome-node" and not config.chrome_node.node)
                else (
                    f"Chrome node pinned to {config.chrome_node.node}"
                    if config.chrome_node.node
                    else "Chrome node not pinned; automatic selection works when exactly one capable node is connected"
                )
            ),
        )
    )

    if needs_chrome_realtime_audio:
        wait_ok = config.chrome.wait_for_in_call_ms > 0
        checks.append(
            SetupCheck(
                id="intro-after-in-call",
                ok=wait_ok,
                message=(
                    f"Realtime intro waits up to {config.chrome.wait_for_in_call_ms}ms for the Meet tab to be in-call"
                    if wait_ok
                    else "Set chrome.waitForInCallMs to delay realtime intro until the Meet tab is in-call"
                ),
            )
        )

    if resolved_transport == "twilio":
        has_req_plan = bool(twilio_dial_in_number)
        has_default_plan = bool(config.twilio.default_dial_in_number)
        has_plan = has_req_plan or has_default_plan
        checks.append(
            SetupCheck(
                id="twilio-dial-plan",
                ok=has_plan,
                message=(
                    "Twilio request includes a Meet dial-in number"
                    if has_req_plan
                    else (
                        "Twilio default Meet dial-in number is configured"
                        if has_default_plan
                        else "Twilio joins require a Meet dial-in phone number; pass dialInNumber with optional pin/dtmfSequence or configure twilio.defaultDialInNumber"
                    )
                ),
            )
        )

    should_check_twilio_delegation = config.voice_call.enabled and (
        resolved_transport == "twilio"
        or bool(config.twilio.default_dial_in_number)
        or "voice-call" in plugin_entries
    )
    if should_check_twilio_delegation:
        plugin_allow = plugins_dict.get("allow")
        voice_call_allowed = not isinstance(plugin_allow, list) or "voice-call" in plugin_allow
        has_voice_call_entry = "voice-call" in plugin_entries
        voice_call_enabled = has_voice_call_entry and voice_call_entry.get("enabled") is not False
        vc_ok = voice_call_allowed and voice_call_enabled
        checks.append(
            SetupCheck(
                id="twilio-voice-call-plugin",
                ok=vc_ok,
                message=(
                    "Twilio transport can delegate dialing to the voice-call plugin"
                    if vc_ok
                    else "Enable plugins.entries.voice-call and include voice-call in plugins.allow for Twilio dialing"
                ),
            )
        )

        provider = voice_call_config.get("provider") or "twilio"
        if provider == "twilio":
            acc_sid = voice_call_twilio_config.get("accountSid") or environ.get(
                "TWILIO_ACCOUNT_SID"
            )
            auth_token = voice_call_twilio_config.get("authToken") or environ.get(
                "TWILIO_AUTH_TOKEN"
            )
            from_num = voice_call_config.get("fromNumber") or environ.get("TWILIO_FROM_NUMBER")
            twilio_ready = bool(acc_sid and auth_token and from_num)
            checks.append(
                SetupCheck(
                    id="twilio-voice-call-credentials",
                    ok=twilio_ready,
                    message=(
                        "Twilio voice-call credentials are configured"
                        if twilio_ready
                        else "Set TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, and TWILIO_FROM_NUMBER or configure voice-call Twilio credentials"
                    ),
                )
            )
            checks.append(get_voice_call_webhook_exposure_check(voice_call_config))

    all_ok = all(c.ok for c in checks)
    return GoogleMeetSetupStatus(ok=all_ok, checks=checks)


def add_google_meet_setup_check(
    status: GoogleMeetSetupStatus,
    check: SetupCheck,
) -> GoogleMeetSetupStatus:
    new_checks = list(status.checks) + [check]
    return GoogleMeetSetupStatus(ok=all(c.ok for c in new_checks), checks=new_checks)


inspect_google_meet_setup_status = get_google_meet_setup_status
