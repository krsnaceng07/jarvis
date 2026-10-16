"""Pre-flight diagnostic checks and setup verification for Voice Call."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from .config import VoiceCallConfig
from .webhook_utils import is_provider_unreachable_webhook_url, resolve_public_webhook_url


@dataclass(slots=True)
class VoiceCallSetupCheck:
    id: str
    ok: bool
    message: str


@dataclass(slots=True)
class VoiceCallSetupStatus:
    ok: bool
    checks: list[VoiceCallSetupCheck] = field(default_factory=list)


def get_voice_call_setup_status(
    config: VoiceCallConfig,
    *,
    env: dict[str, str] | None = None,
    full_config: Any = None,
) -> VoiceCallSetupStatus:
    """Evaluate Voice Call plugin readiness and pre-flight health."""
    checks: list[VoiceCallSetupCheck] = []
    environ = env if env is not None else dict(os.environ)

    # 1. Plugin enablement
    checks.append(
        VoiceCallSetupCheck(
            id="voice-call-enabled",
            ok=config.enabled,
            message=(
                "Voice Call plugin is enabled"
                if config.enabled
                else "Voice Call plugin is disabled (set plugins.entries.voice-call.enabled: true)"
            ),
        )
    )

    # 2. Provider credentials
    prov = config.provider
    if prov == "twilio":
        has_sid = bool(config.twilio.account_sid or environ.get("TWILIO_ACCOUNT_SID"))
        has_secret = bool(
            config.twilio.auth_token
            or config.twilio.api_secret
            or environ.get("TWILIO_AUTH_TOKEN")
            or environ.get("TWILIO_API_SECRET")
        )
        has_from = bool(config.from_number or environ.get("TWILIO_FROM_NUMBER"))
        ok_creds = has_sid and has_secret and has_from
        checks.append(
            VoiceCallSetupCheck(
                id="twilio-credentials",
                ok=ok_creds,
                message=(
                    "Twilio account SID, auth token, and fromNumber configured"
                    if ok_creds
                    else "Missing Twilio credentials (set twilio.accountSid, twilio.authToken, and fromNumber, or TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, and TWILIO_FROM_NUMBER)"
                ),
            )
        )
    elif prov == "telnyx":
        has_key = bool(config.telnyx.api_key or environ.get("TELNYX_API_KEY"))
        has_conn = bool(config.telnyx.connection_id or environ.get("TELNYX_CONNECTION_ID"))
        has_pub = bool(config.telnyx.public_key or environ.get("TELNYX_PUBLIC_KEY"))
        has_from = bool(config.from_number or environ.get("TELNYX_FROM_NUMBER"))
        ok_creds = has_key and has_conn and has_pub and has_from
        checks.append(
            VoiceCallSetupCheck(
                id="telnyx-credentials",
                ok=ok_creds,
                message=(
                    "Telnyx API key, connection ID, public key, and fromNumber configured"
                    if ok_creds
                    else "Missing Telnyx credentials (set telnyx.apiKey, telnyx.connectionId, telnyx.publicKey, and fromNumber, or TELNYX_API_KEY, TELNYX_CONNECTION_ID, and TELNYX_PUBLIC_KEY)"
                ),
            )
        )
    elif prov == "plivo":
        has_auth = bool(config.plivo.auth_id or environ.get("PLIVO_AUTH_ID"))
        has_token = bool(config.plivo.auth_token or environ.get("PLIVO_AUTH_TOKEN"))
        has_from = bool(config.from_number or environ.get("PLIVO_FROM_NUMBER"))
        ok_creds = has_auth and has_token and has_from
        checks.append(
            VoiceCallSetupCheck(
                id="plivo-credentials",
                ok=ok_creds,
                message=(
                    "Plivo auth ID, auth token, and fromNumber configured"
                    if ok_creds
                    else "Missing Plivo credentials (set plivo.authId, plivo.authToken, and fromNumber, or PLIVO_AUTH_ID and PLIVO_AUTH_TOKEN)"
                ),
            )
        )
    else:
        # Mock provider
        checks.append(
            VoiceCallSetupCheck(
                id="mock-provider",
                ok=True,
                message="Mock voice provider active (offline development mode)",
            )
        )

    # 3. Webhook exposure check
    if prov != "mock":
        public_url = resolve_public_webhook_url(
            public_url=config.public_url,
            tunnel=config.tunnel,
            tailscale=config.tailscale,
        )
        is_unreachable = is_provider_unreachable_webhook_url(public_url)
        ok_webhook = bool(public_url and not is_unreachable)
        checks.append(
            VoiceCallSetupCheck(
                id="webhook-exposure",
                ok=ok_webhook,
                message=(
                    f"Public webhook exposure configured: {public_url}"
                    if ok_webhook
                    else (
                        f"Webhook URL is local/private space and cannot receive carrier callbacks: {public_url}"
                        if public_url
                        else "No public webhook exposure configured (set publicUrl, tunnel, or tailscale)"
                    )
                ),
            )
        )
    else:
        checks.append(
            VoiceCallSetupCheck(
                id="webhook-exposure",
                ok=True,
                message="Mock provider does not require public webhook exposure",
            )
        )

    # 4. Agent ownership check
    has_agent = bool(config.agent_id and config.agent_id.strip())
    checks.append(
        VoiceCallSetupCheck(
            id="agent-ownership",
            ok=has_agent,
            message=(
                f"Call ownership assigned to agent: {config.agent_id}"
                if has_agent
                else "No agentId configured for call ownership"
            ),
        )
    )

    # 5. Audio mode mutual exclusion
    dual_audio = (
        config.realtime.enabled
        and config.streaming.enabled
        and config.mode not in ("realtime", "streaming")
    )
    checks.append(
        VoiceCallSetupCheck(
            id="only-one-audio-mode-active",
            ok=not dual_audio,
            message=(
                f"Active audio mode configured: {config.mode}"
                if not dual_audio
                else "Both realtime and streaming audio modes are enabled simultaneously without a single active mode"
            ),
        )
    )

    # 6. Inbound policy check
    policy = config.inbound_policy
    if policy == "disabled":
        msg = "Inbound calls are disabled"
    elif policy == "open":
        msg = "Inbound calls are open to all callers"
    elif policy == "allowlist":
        msg = f"Inbound calls restricted to allowlist ({len(config.allow_from)} number(s))"
    else:
        msg = "Inbound calls require device pairing"

    checks.append(
        VoiceCallSetupCheck(
            id="inbound-policy",
            ok=True,
            message=msg,
        )
    )

    # 7. Realtime requires non-disabled inbound policy
    if config.realtime.enabled:
        rt_inbound_ok = config.inbound_policy != "disabled"
        checks.append(
            VoiceCallSetupCheck(
                id="realtime-inbound-policy",
                ok=rt_inbound_ok,
                message=(
                    "Inbound policy configured for realtime audio"
                    if rt_inbound_ok
                    else "inboundPolicy cannot be 'disabled' when realtime.enabled is true"
                ),
            )
        )

    # 8. Streaming requires provider: twilio
    if config.streaming.enabled:
        st_tw_ok = config.provider == "twilio"
        checks.append(
            VoiceCallSetupCheck(
                id="streaming-twilio-only",
                ok=st_tw_ok,
                message=(
                    "Twilio provider active for streaming transcription"
                    if st_tw_ok
                    else f"Streaming transcription requires provider: twilio (got '{config.provider}')"
                ),
            )
        )

    all_ok = all(c.ok for c in checks)
    return VoiceCallSetupStatus(ok=all_ok, checks=checks)
