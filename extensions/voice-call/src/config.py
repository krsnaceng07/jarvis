"""Configuration schemas, resolution, and validation for the Voice Call plugin."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from jarvis_sdk import Err, Ok, Result

from .phone_utils import normalize_e164_phone_number
from .secret_ref import resolve_secret_value

VoiceCallProvider = Literal["mock", "plivo", "telnyx", "twilio"]
VoiceCallInboundPolicy = Literal["disabled", "allowlist", "pairing", "open"]
VoiceCallSessionScope = Literal["per-phone", "per-call", "main"]
VoiceCallAudioMode = Literal["notify", "turn", "realtime", "streaming"]


@dataclass(slots=True)
class VoiceCallTwilioConfig:
    account_sid: str | None = None
    auth_token: str | None = None
    api_key: str | None = None
    api_secret: str | None = None
    twiml_app_sid: str | None = None
    status_callback_url: str | None = None
    region: str = "us1"  # "us1" | "ie1" | "au1"


@dataclass(slots=True)
class VoiceCallTelnyxConfig:
    api_key: str | None = None
    connection_id: str | None = None
    public_key: str | None = None


@dataclass(slots=True)
class VoiceCallPlivoConfig:
    auth_id: str | None = None
    auth_token: str | None = None
    app_id: str | None = None


@dataclass(slots=True)
class VoiceCallMockConfig:
    auto_answer: bool = True
    simulate_network_delay_ms: int = 0


@dataclass(slots=True)
class VoiceCallServeConfig:
    port: int = 3334
    path: str = "/voice/webhook"
    bind: str = "127.0.0.1"


@dataclass(slots=True)
class VoiceCallWebhookSecurityConfig:
    allowed_hosts: list[str] = field(default_factory=list)
    trust_forwarding_headers: bool = False
    trusted_proxy_ips: list[str] = field(default_factory=list)
    validate_signature: bool = True


@dataclass(slots=True)
class VoiceCallTTSConfig:
    provider: str | None = None  # "core", "elevenlabs", "openai"
    voice: str | None = None
    model: str | None = None
    options: dict[str, Any] = field(default_factory=dict)
    providers: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class VoiceCallAgentContextConfig:
    enabled: bool = False
    max_chars: int = 6000
    include_identity: bool = True
    include_workspace_files: bool = True
    files: list[str] = field(default_factory=lambda: ["SOUL.md", "IDENTITY.md", "USER.md"])


@dataclass(slots=True)
class VoiceCallFastContextConfig:
    enabled: bool = False
    timeout_ms: int = 1500
    fallback_to_consult: bool = True


@dataclass(slots=True)
class VoiceCallRealtimeConfig:
    enabled: bool = False
    provider: str = "google"  # "google" | "openai"
    model: str | None = None
    voice: str | None = None
    instructions: str | None = None
    temperature: float | None = None
    tool_policy: str = "safe-read-only"  # "safe-read-only" | "owner" | "none"
    consult_policy: str = "auto"  # "auto" | "substantive" | "always"
    consult_thinking_level: str = "low"  # "low" | "medium" | "high"
    consult_fast_mode: bool = True
    agent_context: VoiceCallAgentContextConfig = field(default_factory=VoiceCallAgentContextConfig)
    fast_context: VoiceCallFastContextConfig = field(default_factory=VoiceCallFastContextConfig)
    turn_detection: dict[str, Any] = field(default_factory=dict)
    tools: list[dict[str, Any]] = field(default_factory=list)
    providers: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class VoiceCallStreamingConfig:
    enabled: bool = False
    provider: str = "openai"  # "deepgram" | "elevenlabs" | "mistral" | "openai" | "xai"
    model: str | None = None
    language: str | None = None
    stream_path: str = "/voice/stream"
    pre_start_timeout_ms: int = 5000
    max_pending_connections: int = 32
    max_pending_connections_per_ip: int = 4
    max_connections: int = 128
    providers: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class VoiceCallOutboundConfig:
    default_mode: str = "notify"  # "notify" | "conversation" | "turn"
    notify_hangup_delay_sec: int = 3


@dataclass(slots=True)
class VoiceCallNumberRouting:
    number: str
    agent_id: str | None = None
    inbound_policy: VoiceCallInboundPolicy | None = None
    inbound_greeting: str | None = None
    response_model: str | None = None
    response_system_prompt: str | None = None
    response_timeout_ms: int | None = None
    tts: VoiceCallTTSConfig | None = None
    realtime: VoiceCallRealtimeConfig | None = None
    greeting: str | None = None

    @property
    def effective_greeting(self) -> str | None:
        return self.inbound_greeting or self.greeting


@dataclass(slots=True)
class VoiceCallConfig:
    enabled: bool = False
    provider: VoiceCallProvider = "twilio"
    from_number: str | None = None
    to_number: str | None = None
    inbound_policy: VoiceCallInboundPolicy = "disabled"
    allow_from: list[str] = field(default_factory=list)
    session_scope: VoiceCallSessionScope = "per-phone"
    max_duration_seconds: int = 300
    stale_call_reaper_seconds: int = 120
    silence_timeout_ms: int = 800
    transcript_timeout_ms: int = 180000
    ring_timeout_ms: int = 30000
    max_concurrent_calls: int = 1
    skip_signature_verification: bool = False
    store: str | None = None
    agent_id: str = "main"
    response_model: str | None = None
    response_system_prompt: str | None = None
    response_timeout_ms: int = 30000
    public_url: str | None = None
    tunnel: dict[str, Any] = field(default_factory=dict)
    tailscale: dict[str, Any] = field(default_factory=dict)
    mode: VoiceCallAudioMode = "turn"
    serve: VoiceCallServeConfig = field(default_factory=VoiceCallServeConfig)
    outbound: VoiceCallOutboundConfig = field(default_factory=VoiceCallOutboundConfig)
    twilio: VoiceCallTwilioConfig = field(default_factory=VoiceCallTwilioConfig)
    telnyx: VoiceCallTelnyxConfig = field(default_factory=VoiceCallTelnyxConfig)
    plivo: VoiceCallPlivoConfig = field(default_factory=VoiceCallPlivoConfig)
    mock: VoiceCallMockConfig = field(default_factory=VoiceCallMockConfig)
    webhook_security: VoiceCallWebhookSecurityConfig = field(
        default_factory=VoiceCallWebhookSecurityConfig
    )
    tts: VoiceCallTTSConfig = field(default_factory=VoiceCallTTSConfig)
    realtime: VoiceCallRealtimeConfig = field(default_factory=VoiceCallRealtimeConfig)
    streaming: VoiceCallStreamingConfig = field(default_factory=VoiceCallStreamingConfig)
    numbers: dict[str, VoiceCallNumberRouting] = field(default_factory=dict)
    spoken_output: dict[str, Any] = field(default_factory=dict)
    disconnect_grace_seconds: float = 5.0


def resolve_voice_call_config(
    raw_config: dict[str, Any] | None,
    env: dict[str, str] | None = None,
) -> Result[VoiceCallConfig, str]:
    """Parse and validate raw plugin configuration dictionary into canonical VoiceCallConfig."""
    data = raw_config if isinstance(raw_config, dict) else {}

    enabled = bool(data.get("enabled", False))

    raw_prov = str(data.get("provider") or "twilio").strip().lower()
    provider: VoiceCallProvider = (
        raw_prov if raw_prov in ("mock", "plivo", "telnyx", "twilio") else "twilio"
    )

    from_number = data.get("fromNumber") or data.get("from_number")
    normalized_from: str | None = None
    if from_number:
        try:
            normalized_from = normalize_e164_phone_number(str(from_number))
        except ValueError:
            normalized_from = str(from_number).strip()

    to_number = data.get("toNumber") or data.get("to_number")
    normalized_to: str | None = None
    if to_number:
        try:
            normalized_to = normalize_e164_phone_number(str(to_number))
        except ValueError:
            normalized_to = str(to_number).strip()

    raw_inbound = (
        str(data.get("inboundPolicy") or data.get("inbound_policy") or "disabled").strip().lower()
    )
    inbound_policy: VoiceCallInboundPolicy = (
        raw_inbound if raw_inbound in ("disabled", "allowlist", "pairing", "open") else "disabled"
    )

    raw_allow = data.get("allowFrom") or data.get("allow_from") or []
    allow_from: list[str] = []
    if isinstance(raw_allow, list):
        for item in raw_allow:
            if isinstance(item, str) and item.strip():
                try:
                    allow_from.append(normalize_e164_phone_number(item.strip()))
                except ValueError:
                    allow_from.append(item.strip())

    raw_scope = (
        str(data.get("sessionScope") or data.get("session_scope") or "per-phone").strip().lower()
    )
    session_scope: VoiceCallSessionScope = (
        raw_scope if raw_scope in ("per-phone", "per-call", "main") else "per-phone"
    )

    max_duration = int(data.get("maxDurationSeconds") or data.get("max_duration_seconds") or 300)
    stale_reaper = int(
        data.get("staleCallReaperSeconds")
        if "staleCallReaperSeconds" in data
        else data.get("stale_call_reaper_seconds", 120)
    )
    silence_timeout = int(data.get("silenceTimeoutMs") or data.get("silence_timeout_ms") or 800)
    transcript_timeout = int(
        data.get("transcriptTimeoutMs") or data.get("transcript_timeout_ms") or 180000
    )
    ring_timeout = int(data.get("ringTimeoutMs") or data.get("ring_timeout_ms") or 30000)
    max_concurrent = int(data.get("maxConcurrentCalls") or data.get("max_concurrent_calls") or 1)
    skip_sig = bool(
        data.get("skipSignatureVerification", data.get("skip_signature_verification", False))
    )
    store_override = data.get("store")

    agent_id = str(data.get("agentId") or data.get("agent_id") or "main").strip() or "main"
    resp_model = data.get("responseModel") or data.get("response_model")
    resp_prompt = data.get("responseSystemPrompt") or data.get("response_system_prompt")
    resp_timeout = int(data.get("responseTimeoutMs") or data.get("response_timeout_ms") or 30000)

    public_url = data.get("publicUrl") or data.get("public_url")
    tunnel = data.get("tunnel") if isinstance(data.get("tunnel"), dict) else {}
    tailscale = data.get("tailscale") if isinstance(data.get("tailscale"), dict) else {}

    raw_mode = str(data.get("mode") or "turn").strip().lower()
    mode: VoiceCallAudioMode = (
        raw_mode if raw_mode in ("notify", "turn", "realtime", "streaming") else "turn"
    )

    # Serve config
    raw_serve = data.get("serve") if isinstance(data.get("serve"), dict) else {}
    serve = VoiceCallServeConfig(
        port=int(raw_serve.get("port", 3334)),
        path=str(raw_serve.get("path", "/voice/webhook")),
        bind=str(raw_serve.get("bind", "127.0.0.1")),
    )

    # Outbound config
    raw_outbound = data.get("outbound") if isinstance(data.get("outbound"), dict) else {}
    outbound = VoiceCallOutboundConfig(
        default_mode=str(
            raw_outbound.get("defaultMode", raw_outbound.get("default_mode", "notify"))
        ),
        notify_hangup_delay_sec=int(
            raw_outbound.get("notifyHangupDelaySec", raw_outbound.get("notify_hangup_delay_sec", 3))
        ),
    )

    # Provider configs (with SecretRef resolution)
    raw_twilio = data.get("twilio") if isinstance(data.get("twilio"), dict) else {}
    twilio_token_raw = raw_twilio.get("authToken") or raw_twilio.get("auth_token")
    twilio_secret_raw = raw_twilio.get("apiSecret") or raw_twilio.get("api_secret")
    twilio = VoiceCallTwilioConfig(
        account_sid=resolve_secret_value(
            raw_twilio.get("accountSid") or raw_twilio.get("account_sid"), env
        ),
        auth_token=resolve_secret_value(twilio_token_raw, env),
        api_key=resolve_secret_value(raw_twilio.get("apiKey") or raw_twilio.get("api_key"), env),
        api_secret=resolve_secret_value(twilio_secret_raw, env),
        twiml_app_sid=raw_twilio.get("twimlAppSid") or raw_twilio.get("twiml_app_sid"),
        status_callback_url=raw_twilio.get("statusCallbackUrl")
        or raw_twilio.get("status_callback_url"),
        region=str(raw_twilio.get("region", "us1")).strip().lower() or "us1",
    )

    raw_telnyx = data.get("telnyx") if isinstance(data.get("telnyx"), dict) else {}
    telnyx = VoiceCallTelnyxConfig(
        api_key=resolve_secret_value(raw_telnyx.get("apiKey") or raw_telnyx.get("api_key"), env),
        connection_id=raw_telnyx.get("connectionId") or raw_telnyx.get("connection_id"),
        public_key=resolve_secret_value(
            raw_telnyx.get("publicKey") or raw_telnyx.get("public_key"), env
        ),
    )

    raw_plivo = data.get("plivo") if isinstance(data.get("plivo"), dict) else {}
    plivo = VoiceCallPlivoConfig(
        auth_id=raw_plivo.get("authId") or raw_plivo.get("auth_id"),
        auth_token=resolve_secret_value(
            raw_plivo.get("authToken") or raw_plivo.get("auth_token"), env
        ),
        app_id=raw_plivo.get("appId") or raw_plivo.get("app_id"),
    )

    raw_mock = data.get("mock") if isinstance(data.get("mock"), dict) else {}
    mock = VoiceCallMockConfig(
        auto_answer=bool(raw_mock.get("autoAnswer", raw_mock.get("auto_answer", True))),
        simulate_network_delay_ms=int(
            raw_mock.get("simulateNetworkDelayMs", raw_mock.get("simulate_network_delay_ms", 0))
        ),
    )

    raw_sec = data.get("webhookSecurity") or data.get("webhook_security") or {}
    sec_dict = raw_sec if isinstance(raw_sec, dict) else {}
    webhook_security = VoiceCallWebhookSecurityConfig(
        allowed_hosts=list(sec_dict.get("allowedHosts") or sec_dict.get("allowed_hosts") or []),
        trust_forwarding_headers=bool(
            sec_dict.get("trustForwardingHeaders", sec_dict.get("trust_forwarding_headers", False))
        ),
        trusted_proxy_ips=list(
            sec_dict.get("trustedProxyIPs") or sec_dict.get("trusted_proxy_ips") or []
        ),
        validate_signature=bool(
            sec_dict.get("validateSignature", sec_dict.get("validate_signature", True))
        ),
    )

    raw_tts = data.get("tts") if isinstance(data.get("tts"), dict) else {}
    tts = VoiceCallTTSConfig(
        provider=raw_tts.get("provider"),
        voice=raw_tts.get("voice"),
        model=raw_tts.get("model"),
        options=raw_tts.get("options") if isinstance(raw_tts.get("options"), dict) else {},
        providers=raw_tts.get("providers") if isinstance(raw_tts.get("providers"), dict) else {},
    )

    raw_realtime = data.get("realtime") if isinstance(data.get("realtime"), dict) else {}
    raw_ac = (
        raw_realtime.get("agentContext")
        if isinstance(raw_realtime.get("agentContext"), dict)
        else {}
    )
    agent_ctx = VoiceCallAgentContextConfig(
        enabled=bool(raw_ac.get("enabled", False)),
        max_chars=int(raw_ac.get("maxChars", 6000)),
        include_identity=bool(raw_ac.get("includeIdentity", True)),
        include_workspace_files=bool(raw_ac.get("includeWorkspaceFiles", True)),
        files=list(raw_ac.get("files", ["SOUL.md", "IDENTITY.md", "USER.md"])),
    )

    raw_fc = (
        raw_realtime.get("fastContext") if isinstance(raw_realtime.get("fastContext"), dict) else {}
    )
    fast_ctx = VoiceCallFastContextConfig(
        enabled=bool(raw_fc.get("enabled", False)),
        timeout_ms=int(raw_fc.get("timeoutMs", 1500)),
        fallback_to_consult=bool(raw_fc.get("fallbackToConsult", True)),
    )

    realtime = VoiceCallRealtimeConfig(
        enabled=bool(raw_realtime.get("enabled", mode == "realtime")),
        provider=str(raw_realtime.get("provider") or "google").strip().lower(),
        model=raw_realtime.get("model"),
        voice=raw_realtime.get("voice") or raw_realtime.get("speakerVoice"),
        instructions=raw_realtime.get("instructions"),
        temperature=float(raw_realtime["temperature"]) if "temperature" in raw_realtime else None,
        tool_policy=str(raw_realtime.get("toolPolicy", "safe-read-only")).strip().lower(),
        consult_policy=str(raw_realtime.get("consultPolicy", "auto")).strip().lower(),
        consult_thinking_level=str(raw_realtime.get("consultThinkingLevel", "low")).strip().lower(),
        consult_fast_mode=bool(raw_realtime.get("consultFastMode", True)),
        agent_context=agent_ctx,
        fast_context=fast_ctx,
        turn_detection=raw_realtime.get("turnDetection")
        if isinstance(raw_realtime.get("turnDetection"), dict)
        else {},
        tools=list(raw_realtime.get("tools", []))
        if isinstance(raw_realtime.get("tools"), list)
        else [],
        providers=raw_realtime.get("providers")
        if isinstance(raw_realtime.get("providers"), dict)
        else {},
    )

    raw_streaming = data.get("streaming") if isinstance(data.get("streaming"), dict) else {}
    streaming = VoiceCallStreamingConfig(
        enabled=bool(raw_streaming.get("enabled", mode == "streaming")),
        provider=str(raw_streaming.get("provider") or "openai").strip().lower(),
        model=raw_streaming.get("model"),
        language=raw_streaming.get("language"),
        stream_path=str(raw_streaming.get("streamPath", "/voice/stream")),
        pre_start_timeout_ms=int(raw_streaming.get("preStartTimeoutMs", 5000)),
        max_pending_connections=int(raw_streaming.get("maxPendingConnections", 32)),
        max_pending_connections_per_ip=int(raw_streaming.get("maxPendingConnectionsPerIp", 4)),
        max_connections=int(raw_streaming.get("maxConnections", 128)),
        providers=raw_streaming.get("providers")
        if isinstance(raw_streaming.get("providers"), dict)
        else {},
    )

    # Per-number routing table
    numbers: dict[str, VoiceCallNumberRouting] = {}
    raw_numbers = data.get("numbers") if isinstance(data.get("numbers"), dict) else {}
    for num_key, num_val in raw_numbers.items():
        if isinstance(num_val, dict):
            num_inbound = str(num_val.get("inboundPolicy") or "").strip().lower()
            inbound_mapped: VoiceCallInboundPolicy | None = (
                num_inbound if num_inbound in ("disabled", "allowlist", "pairing", "open") else None  # type: ignore[assignment]
            )
            n_tts = None
            if "tts" in num_val and isinstance(num_val["tts"], dict):
                n_tts = VoiceCallTTSConfig(
                    provider=num_val["tts"].get("provider"),
                    voice=num_val["tts"].get("voice"),
                    model=num_val["tts"].get("model"),
                    options=num_val["tts"].get("options")
                    if isinstance(num_val["tts"].get("options"), dict)
                    else {},
                    providers=num_val["tts"].get("providers")
                    if isinstance(num_val["tts"].get("providers"), dict)
                    else {},
                )
            n_realtime = None
            if "realtime" in num_val and isinstance(num_val["realtime"], dict):
                n_realtime = VoiceCallRealtimeConfig(
                    enabled=bool(num_val["realtime"].get("enabled", True)),
                    provider=str(num_val["realtime"].get("provider") or "gemini"),
                    model=num_val["realtime"].get("model"),
                    voice=num_val["realtime"].get("voice"),
                    instructions=num_val["realtime"].get("instructions"),
                    providers=num_val["realtime"].get("providers")
                    if isinstance(num_val["realtime"].get("providers"), dict)
                    else {},
                )
            norm_key = num_key
            try:
                norm_key = normalize_e164_phone_number(num_key)
            except ValueError:
                pass
            numbers[norm_key] = VoiceCallNumberRouting(
                number=norm_key,
                agent_id=num_val.get("agentId") or num_val.get("agent_id"),
                inbound_policy=inbound_mapped,
                inbound_greeting=num_val.get("inboundGreeting") or num_val.get("inbound_greeting"),
                response_model=num_val.get("responseModel") or num_val.get("response_model"),
                response_system_prompt=num_val.get("responseSystemPrompt")
                or num_val.get("response_system_prompt"),
                response_timeout_ms=int(num_val["responseTimeoutMs"])
                if "responseTimeoutMs" in num_val
                else (
                    int(num_val["response_timeout_ms"])
                    if "response_timeout_ms" in num_val
                    else None
                ),
                tts=n_tts,
                realtime=n_realtime,
            )

    spoken_output = data.get("spokenOutput") if isinstance(data.get("spokenOutput"), dict) else {}
    disconnect_grace = float(
        data.get("disconnectGraceSeconds") or data.get("disconnect_grace_seconds") or 5.0
    )

    cfg = VoiceCallConfig(
        enabled=enabled,
        provider=provider,
        from_number=normalized_from,
        to_number=normalized_to,
        inbound_policy=inbound_policy,
        allow_from=allow_from,
        session_scope=session_scope,
        max_duration_seconds=max_duration,
        stale_call_reaper_seconds=stale_reaper,
        silence_timeout_ms=silence_timeout,
        transcript_timeout_ms=transcript_timeout,
        ring_timeout_ms=ring_timeout,
        max_concurrent_calls=max_concurrent,
        skip_signature_verification=skip_sig,
        store=store_override,
        agent_id=agent_id,
        response_model=resp_model,
        response_system_prompt=resp_prompt,
        response_timeout_ms=resp_timeout,
        public_url=str(public_url).strip() if public_url else None,
        tunnel=tunnel,
        tailscale=tailscale,
        mode=mode,
        serve=serve,
        outbound=outbound,
        twilio=twilio,
        telnyx=telnyx,
        plivo=plivo,
        mock=mock,
        webhook_security=webhook_security,
        tts=tts,
        realtime=realtime,
        streaming=streaming,
        numbers=numbers,
        spoken_output=spoken_output,
        disconnect_grace_seconds=disconnect_grace,
    )

    return Ok(cfg)


def validate_provider_config(config: VoiceCallConfig) -> Result[None, str]:
    """Validate cross-provider constraints for realtime voice and streaming transcription."""
    if config.realtime.enabled and config.inbound_policy == "disabled":
        return Err("inboundPolicy must not be 'disabled' when realtime.enabled is true")

    if config.realtime.enabled and config.streaming.enabled:
        return Err(
            "realtime.enabled cannot be combined with streaming.enabled. Pick one audio mode per call."
        )

    if config.streaming.enabled and config.provider != "twilio":
        return Err(
            f"Streaming transcription requires provider: twilio, but got '{config.provider}'"
        )

    return Ok(None)


validateProviderConfig = validate_provider_config
