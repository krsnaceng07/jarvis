"""Google Meet configuration models, defaults, and resolution logic."""

from __future__ import annotations

import math
import os
import sys
from dataclasses import dataclass, field
from typing import Any, Literal

from jarvis_sdk import Ok, Result

GoogleMeetTransport = Literal["chrome", "chrome-node", "twilio"]
GoogleMeetMode = Literal["agent", "bidi", "transcribe"]
GoogleMeetModeInput = Literal["agent", "bidi", "transcribe", "realtime"]
GoogleMeetRealtimeStrategy = Literal["agent", "bidi"]
GoogleMeetChromeAudioFormat = Literal["pcm16-24khz", "g711-ulaw-8khz"]
MeetingAudioBackendSelection = Literal["auto", "blackhole-2ch", "pipewire-pulse"]
GoogleMeetToolPolicy = Literal["safe-read-only", "owner", "none"]

SOX_DEFAULT_BUFFER_BYTES = 8192
SOX_MIN_BUFFER_BYTES = 17
DEFAULT_GOOGLE_MEET_AUDIO_BUFFER_BYTES = SOX_DEFAULT_BUFFER_BYTES // 2
DEFAULT_GOOGLE_MEET_CHROME_AUDIO_FORMAT: GoogleMeetChromeAudioFormat = "pcm16-24khz"
DEFAULT_GOOGLE_MEET_BARGE_IN_RMS_THRESHOLD = 650.0
DEFAULT_GOOGLE_MEET_BARGE_IN_PEAK_THRESHOLD = 2500.0
DEFAULT_GOOGLE_MEET_BARGE_IN_COOLDOWN_MS = 900

DEFAULT_GOOGLE_MEET_REALTIME_INSTRUCTIONS = (
    "You are joining a private Google Meet as a JARVIS voice transport. "
    "Keep spoken replies brief and natural. In agent mode, wait for JARVIS consult "
    "results and speak them exactly. In bidi mode, answer directly and call "
    "jarvis_agent_consult for deeper reasoning, current information, or tools."
)
DEFAULT_GOOGLE_MEET_REALTIME_INTRO_MESSAGE = "Say exactly: I'm here and listening."


def build_google_meet_audio_commands(
    backend: MeetingAudioBackendSelection,
    format: GoogleMeetChromeAudioFormat,
    buffer_bytes: int,
) -> dict[str, list[str]]:
    pipe_wire = backend == "pipewire-pulse" or (
        backend == "auto" and sys.platform.startswith("linux")
    )
    sample_rate = 8000 if format == "g711-ulaw-8khz" else 24000
    bits = 8 if format == "g711-ulaw-8khz" else 16

    if pipe_wire:
        pulse_format = "ulaw" if format == "g711-ulaw-8khz" else "s16le"
        bytes_per_sample = math.ceil(bits / 8)
        latency_ms = max(1, math.ceil((buffer_bytes / (sample_rate * bytes_per_sample)) * 1000))
        common = [
            "--device=openclaw_meeting_audio",
            f"--format={pulse_format}",
            f"--rate={sample_rate}",
            "--channels=1",
            f"--latency-msec={latency_ms}",
        ]
        return {
            "inputCommand": ["parec", "--raw", *common],
            "outputCommand": ["pacat", "--raw", "--playback", *common],
        }

    wire = (
        ["-t", "raw", "-r", "8000", "-c", "1", "-e", "mu-law", "-b", "8", "-"]
        if format == "g711-ulaw-8khz"
        else ["-t", "raw", "-r", "24000", "-c", "1", "-e", "signed-integer", "-b", "16", "-L", "-"]
    )

    def with_buffer(executable: str, args: list[str]) -> list[str]:
        return [executable, "-q", "--buffer", str(buffer_bytes), *args]

    return {
        "inputCommand": with_buffer("sox", ["-t", "coreaudio", "BlackHole 2ch", *wire]),
        "outputCommand": with_buffer("sox", [*wire, "-t", "coreaudio", "BlackHole 2ch"]),
    }


_DEFAULT_AUDIO_COMMANDS = build_google_meet_audio_commands(
    "blackhole-2ch", "pcm16-24khz", DEFAULT_GOOGLE_MEET_AUDIO_BUFFER_BYTES
)
DEFAULT_GOOGLE_MEET_AUDIO_INPUT_COMMAND = _DEFAULT_AUDIO_COMMANDS["inputCommand"]
DEFAULT_GOOGLE_MEET_AUDIO_OUTPUT_COMMAND = _DEFAULT_AUDIO_COMMANDS["outputCommand"]


@dataclass(slots=True)
class DefaultsConfig:
    meeting: str | None = None


@dataclass(slots=True)
class PreviewConfig:
    enrollment_acknowledged: bool = False


@dataclass(slots=True)
class ChromeConfig:
    audio_backend: MeetingAudioBackendSelection = "auto"
    audio_format: GoogleMeetChromeAudioFormat = "pcm16-24khz"
    audio_buffer_bytes: int = DEFAULT_GOOGLE_MEET_AUDIO_BUFFER_BYTES
    launch: bool = True
    browser_profile: str | None = None
    guest_name: str = "JARVIS Agent"
    reuse_existing_tab: bool = True
    auto_join: bool = True
    join_timeout_ms: int = 30000
    wait_for_in_call_ms: int = 20000
    audio_input_command: list[str] = field(
        default_factory=lambda: list(DEFAULT_GOOGLE_MEET_AUDIO_INPUT_COMMAND)
    )
    audio_output_command: list[str] = field(
        default_factory=lambda: list(DEFAULT_GOOGLE_MEET_AUDIO_OUTPUT_COMMAND)
    )
    audio_input_command_override: list[str] | None = None
    audio_output_command_override: list[str] | None = None
    barge_in_input_command: list[str] | None = None
    barge_in_rms_threshold: float = DEFAULT_GOOGLE_MEET_BARGE_IN_RMS_THRESHOLD
    barge_in_peak_threshold: float = DEFAULT_GOOGLE_MEET_BARGE_IN_PEAK_THRESHOLD
    barge_in_cooldown_ms: int = DEFAULT_GOOGLE_MEET_BARGE_IN_COOLDOWN_MS
    audio_bridge_command: list[str] | None = None
    audio_bridge_health_command: list[str] | None = None


@dataclass(slots=True)
class ChromeNodeConfig:
    node: str | None = None


@dataclass(slots=True)
class TwilioConfig:
    default_dial_in_number: str | None = None
    default_pin: str | None = None
    default_dtmf_sequence: str | None = None


@dataclass(slots=True)
class VoiceCallConfig:
    enabled: bool = True
    gateway_url: str | None = None
    token: str | None = None
    request_timeout_ms: int = 30000
    dtmf_delay_ms: int = 12000
    post_dtmf_speech_delay_ms: int = 5000
    intro_message: str | None = None


@dataclass(slots=True)
class RealtimeConfig:
    strategy: GoogleMeetRealtimeStrategy = "agent"
    provider: str = "openai"
    transcription_provider: str = "openai"
    voice_provider: str | None = None
    model: str | None = None
    instructions: str = DEFAULT_GOOGLE_MEET_REALTIME_INSTRUCTIONS
    intro_message: str = DEFAULT_GOOGLE_MEET_REALTIME_INTRO_MESSAGE
    agent_id: str | None = None
    tool_policy: GoogleMeetToolPolicy = "safe-read-only"
    providers: dict[str, dict[str, Any]] = field(default_factory=dict)


@dataclass(slots=True)
class OAuthConfig:
    client_id: str | None = None
    client_secret: str | None = None
    refresh_token: str | None = None
    access_token: str | None = None
    expires_at: float | None = None


@dataclass(slots=True)
class AuthConfig:
    provider: str = "google-oauth"
    client_id: str | None = None
    client_secret: str | None = None
    token_path: str | None = None


@dataclass(slots=True)
class GoogleMeetConfig:
    enabled: bool = True
    defaults: DefaultsConfig = field(default_factory=DefaultsConfig)
    preview: PreviewConfig = field(default_factory=PreviewConfig)
    default_transport: GoogleMeetTransport = "chrome"
    default_mode: GoogleMeetMode = "agent"
    chrome: ChromeConfig = field(default_factory=ChromeConfig)
    chrome_node: ChromeNodeConfig = field(default_factory=ChromeNodeConfig)
    twilio: TwilioConfig = field(default_factory=TwilioConfig)
    voice_call: VoiceCallConfig = field(default_factory=VoiceCallConfig)
    realtime: RealtimeConfig = field(default_factory=RealtimeConfig)
    oauth: OAuthConfig = field(default_factory=OAuthConfig)
    auth: AuthConfig = field(default_factory=AuthConfig)


def resolve_google_meet_gateway_operation_timeout_ms(config: GoogleMeetConfig) -> int:
    return max(
        60000,
        config.chrome.join_timeout_ms + 30000,
        config.voice_call.request_timeout_ms + 10000,
    )


def _as_record(val: Any) -> dict[str, Any]:
    return val if isinstance(val, dict) else {}


def _as_bool(val: Any, fallback: bool) -> bool:
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        lowered = val.strip().lower()
        if lowered in ("true", "1", "yes", "on"):
            return True
        if lowered in ("false", "0", "no", "off"):
            return False
    return fallback


def _as_num(val: Any, fallback: float) -> float:
    if isinstance(val, (int, float)) and math.isfinite(val) and val > 0:
        return float(val)
    if isinstance(val, str) and val.strip():
        try:
            parsed = float(val.strip())
            if math.isfinite(parsed) and parsed > 0:
                return parsed
        except ValueError:
            pass
    return fallback


def _as_opt_num(val: Any) -> float | None:
    if isinstance(val, (int, float)) and math.isfinite(val):
        return float(val)
    if isinstance(val, str) and val.strip():
        try:
            parsed = float(val.strip())
            if math.isfinite(parsed):
                return parsed
        except ValueError:
            pass
    return None


def _as_opt_str(val: Any) -> str | None:
    if val is None:
        return None
    s = str(val).strip()
    return s if s else None


def _as_str_list(val: Any) -> list[str] | None:
    if isinstance(val, list):
        items = [str(x).strip() for x in val if str(x).strip()]
        return items if items else []
    return None


def _read_env(env: dict[str, str], keys: tuple[str, ...]) -> str | None:
    for k in keys:
        v = env.get(k)
        if v and v.strip():
            return v.strip()
    return None


_CLIENT_ID_KEYS = (
    "JARVIS_GOOGLE_MEET_CLIENT_ID",
    "OPENCLAW_GOOGLE_MEET_CLIENT_ID",
    "GOOGLE_MEET_CLIENT_ID",
)
_CLIENT_SECRET_KEYS = (
    "JARVIS_GOOGLE_MEET_CLIENT_SECRET",
    "OPENCLAW_GOOGLE_MEET_CLIENT_SECRET",
    "GOOGLE_MEET_CLIENT_SECRET",
)
_REFRESH_TOKEN_KEYS = (
    "JARVIS_GOOGLE_MEET_REFRESH_TOKEN",
    "OPENCLAW_GOOGLE_MEET_REFRESH_TOKEN",
    "GOOGLE_MEET_REFRESH_TOKEN",
)
_ACCESS_TOKEN_KEYS = (
    "JARVIS_GOOGLE_MEET_ACCESS_TOKEN",
    "OPENCLAW_GOOGLE_MEET_ACCESS_TOKEN",
    "GOOGLE_MEET_ACCESS_TOKEN",
)
_ACCESS_TOKEN_EXPIRES_AT_KEYS = (
    "JARVIS_GOOGLE_MEET_ACCESS_TOKEN_EXPIRES_AT",
    "OPENCLAW_GOOGLE_MEET_ACCESS_TOKEN_EXPIRES_AT",
    "GOOGLE_MEET_ACCESS_TOKEN_EXPIRES_AT",
)
_DEFAULT_MEETING_KEYS = (
    "JARVIS_GOOGLE_MEET_DEFAULT_MEETING",
    "OPENCLAW_GOOGLE_MEET_DEFAULT_MEETING",
    "GOOGLE_MEET_DEFAULT_MEETING",
)
_PREVIEW_ACK_KEYS = (
    "JARVIS_GOOGLE_MEET_PREVIEW_ACK",
    "OPENCLAW_GOOGLE_MEET_PREVIEW_ACK",
    "GOOGLE_MEET_PREVIEW_ACK",
)


def _resolve_audio_format(val: Any) -> GoogleMeetChromeAudioFormat | None:
    s = _as_opt_str(val)
    if not s:
        return None
    norm = s.lower().replace("_", "-")
    if norm in ("pcm16-24khz", "pcm16-24k", "pcm24", "pcm"):
        return "pcm16-24khz"
    if norm in ("g711-ulaw-8khz", "g711-ulaw-8k", "g711-ulaw", "mulaw", "mu-law"):
        return "g711-ulaw-8khz"
    return None


def _resolve_transport(val: Any, fallback: GoogleMeetTransport) -> GoogleMeetTransport:
    s = _as_opt_str(val)
    if s and s.lower() in ("chrome", "chrome-node", "twilio"):
        return s.lower()  # type: ignore[return-value]
    return fallback


def _resolve_mode(val: Any, fallback: GoogleMeetMode) -> GoogleMeetMode:
    s = _as_opt_str(val)
    if s:
        lowered = s.lower()
        if lowered == "realtime":
            return "agent"
        if lowered in ("agent", "bidi", "transcribe"):
            return lowered  # type: ignore[return-value]
    return fallback


def _resolve_realtime_strategy(
    val: Any, fallback: GoogleMeetRealtimeStrategy
) -> GoogleMeetRealtimeStrategy:
    s = _as_opt_str(val)
    if s and s.lower() in ("agent", "bidi"):
        return s.lower()  # type: ignore[return-value]
    return fallback


def _resolve_audio_backend(val: Any) -> MeetingAudioBackendSelection:
    s = _as_opt_str(val)
    if s:
        norm = s.lower().replace("_", "-")
        if norm in ("blackhole-2ch", "pipewire-pulse"):
            return norm  # type: ignore[return-value]
    return "auto"


GoogleMeetResolvedConfig = GoogleMeetConfig


def resolve_google_meet_config(
    input_val: Any, env: dict[str, str] | None = None
) -> Result[GoogleMeetConfig, str]:
    env_vars = os.environ.copy() if env is None else env
    raw = _as_record(input_val)
    defaults_raw = _as_record(raw.get("defaults"))
    preview_raw = _as_record(raw.get("preview"))
    chrome_raw = _as_record(raw.get("chrome"))
    chrome_node_raw = _as_record(raw.get("chromeNode"))
    twilio_raw = _as_record(raw.get("twilio"))
    voice_call_raw = _as_record(raw.get("voiceCall"))
    realtime_raw = _as_record(raw.get("realtime"))
    oauth_raw = _as_record(raw.get("oauth"))
    auth_raw = _as_record(raw.get("auth"))

    configured_input_cmd = _as_str_list(chrome_raw.get("audioInputCommand"))
    configured_output_cmd = _as_str_list(chrome_raw.get("audioOutputCommand"))
    has_custom_audio = configured_input_cmd is not None or configured_output_cmd is not None

    audio_format = _resolve_audio_format(chrome_raw.get("audioFormat")) or (
        "g711-ulaw-8khz" if has_custom_audio else DEFAULT_GOOGLE_MEET_CHROME_AUDIO_FORMAT
    )
    raw_buffer_bytes = _as_num(
        chrome_raw.get("audioBufferBytes"), float(DEFAULT_GOOGLE_MEET_AUDIO_BUFFER_BYTES)
    )
    audio_buffer_bytes = max(SOX_MIN_BUFFER_BYTES, int(raw_buffer_bytes))
    audio_backend = _resolve_audio_backend(chrome_raw.get("audioBackend"))

    default_cmds = build_google_meet_audio_commands(audio_backend, audio_format, audio_buffer_bytes)
    resolved_input_cmd = (
        configured_input_cmd if configured_input_cmd is not None else default_cmds["inputCommand"]
    )
    resolved_output_cmd = (
        configured_output_cmd
        if configured_output_cmd is not None
        else default_cmds["outputCommand"]
    )

    # Preview ack env
    env_preview_ack = _read_env(env_vars, _PREVIEW_ACK_KEYS)
    preview_ack = _as_bool(
        preview_raw.get("enrollmentAcknowledged"), _as_bool(env_preview_ack, False)
    )

    # Realtime provider resolution
    rt_provider = _as_opt_str(realtime_raw.get("provider")) or "openai"
    rt_transcription_provider = _as_opt_str(realtime_raw.get("transcriptionProvider"))
    if not rt_transcription_provider:
        rt_transcription_provider = (
            rt_provider if (rt_provider and rt_provider != "google") else "openai"
        )

    providers_raw = _as_record(realtime_raw.get("providers"))
    resolved_providers: dict[str, dict[str, Any]] = {}
    for k, v in providers_raw.items():
        k_str = _as_opt_str(k)
        if k_str:
            resolved_providers[k_str.lower()] = _as_record(v)

    # Tool policy
    raw_tool_policy = _as_opt_str(realtime_raw.get("toolPolicy"))
    tool_policy: GoogleMeetToolPolicy = (
        raw_tool_policy  # type: ignore[assignment]
        if raw_tool_policy in ("safe-read-only", "owner", "none")
        else "safe-read-only"
    )

    cfg = GoogleMeetConfig(
        enabled=_as_bool(raw.get("enabled"), True),
        defaults=DefaultsConfig(
            meeting=_as_opt_str(defaults_raw.get("meeting"))
            or _read_env(env_vars, _DEFAULT_MEETING_KEYS),
        ),
        preview=PreviewConfig(
            enrollment_acknowledged=preview_ack,
        ),
        default_transport=_resolve_transport(raw.get("defaultTransport"), "chrome"),
        default_mode=_resolve_mode(raw.get("defaultMode"), "agent"),
        chrome=ChromeConfig(
            audio_backend=audio_backend,
            audio_format=audio_format,
            audio_buffer_bytes=audio_buffer_bytes,
            launch=_as_bool(chrome_raw.get("launch"), True),
            browser_profile=_as_opt_str(chrome_raw.get("browserProfile")),
            guest_name=_as_opt_str(chrome_raw.get("guestName")) or "JARVIS Agent",
            reuse_existing_tab=_as_bool(chrome_raw.get("reuseExistingTab"), True),
            auto_join=_as_bool(chrome_raw.get("autoJoin"), True),
            join_timeout_ms=int(_as_num(chrome_raw.get("joinTimeoutMs"), 30000)),
            wait_for_in_call_ms=int(_as_num(chrome_raw.get("waitForInCallMs"), 20000)),
            audio_input_command=resolved_input_cmd,
            audio_output_command=resolved_output_cmd,
            audio_input_command_override=configured_input_cmd,
            audio_output_command_override=configured_output_cmd,
            barge_in_input_command=_as_str_list(chrome_raw.get("bargeInInputCommand")),
            barge_in_rms_threshold=_as_num(
                chrome_raw.get("bargeInRmsThreshold"), DEFAULT_GOOGLE_MEET_BARGE_IN_RMS_THRESHOLD
            ),
            barge_in_peak_threshold=_as_num(
                chrome_raw.get("bargeInPeakThreshold"), DEFAULT_GOOGLE_MEET_BARGE_IN_PEAK_THRESHOLD
            ),
            barge_in_cooldown_ms=int(
                _as_num(
                    chrome_raw.get("bargeInCooldownMs"), DEFAULT_GOOGLE_MEET_BARGE_IN_COOLDOWN_MS
                )
            ),
            audio_bridge_command=_as_str_list(chrome_raw.get("audioBridgeCommand")),
            audio_bridge_health_command=_as_str_list(chrome_raw.get("audioBridgeHealthCommand")),
        ),
        chrome_node=ChromeNodeConfig(
            node=_as_opt_str(chrome_node_raw.get("node")),
        ),
        twilio=TwilioConfig(
            default_dial_in_number=_as_opt_str(twilio_raw.get("defaultDialInNumber")),
            default_pin=_as_opt_str(twilio_raw.get("defaultPin")),
            default_dtmf_sequence=_as_opt_str(twilio_raw.get("defaultDtmfSequence")),
        ),
        voice_call=VoiceCallConfig(
            enabled=_as_bool(voice_call_raw.get("enabled"), True),
            gateway_url=_as_opt_str(voice_call_raw.get("gatewayUrl")),
            token=_as_opt_str(voice_call_raw.get("token")),
            request_timeout_ms=int(_as_num(voice_call_raw.get("requestTimeoutMs"), 30000)),
            dtmf_delay_ms=int(_as_num(voice_call_raw.get("dtmfDelayMs"), 12000)),
            post_dtmf_speech_delay_ms=int(
                _as_num(voice_call_raw.get("postDtmfSpeechDelayMs"), 5000)
            ),
            intro_message=_as_opt_str(voice_call_raw.get("introMessage")),
        ),
        realtime=RealtimeConfig(
            strategy=_resolve_realtime_strategy(realtime_raw.get("strategy"), "agent"),
            provider=rt_provider,
            transcription_provider=rt_transcription_provider,
            voice_provider=_as_opt_str(realtime_raw.get("voiceProvider")),
            model=_as_opt_str(realtime_raw.get("model")),
            instructions=_as_opt_str(realtime_raw.get("instructions"))
            or DEFAULT_GOOGLE_MEET_REALTIME_INSTRUCTIONS,
            intro_message=(
                str(realtime_raw["introMessage"]).strip()
                if "introMessage" in realtime_raw and isinstance(realtime_raw["introMessage"], str)
                else DEFAULT_GOOGLE_MEET_REALTIME_INTRO_MESSAGE
            ),
            agent_id=_as_opt_str(realtime_raw.get("agentId")),
            tool_policy=tool_policy,
            providers=resolved_providers,
        ),
        oauth=OAuthConfig(
            client_id=(
                _as_opt_str(oauth_raw.get("clientId"))
                or _as_opt_str(auth_raw.get("clientId"))
                or _read_env(env_vars, _CLIENT_ID_KEYS)
            ),
            client_secret=(
                _as_opt_str(oauth_raw.get("clientSecret"))
                or _as_opt_str(auth_raw.get("clientSecret"))
                or _read_env(env_vars, _CLIENT_SECRET_KEYS)
            ),
            refresh_token=(
                _as_opt_str(oauth_raw.get("refreshToken"))
                or _read_env(env_vars, _REFRESH_TOKEN_KEYS)
            ),
            access_token=(
                _as_opt_str(oauth_raw.get("accessToken")) or _read_env(env_vars, _ACCESS_TOKEN_KEYS)
            ),
            expires_at=(
                _as_opt_num(oauth_raw.get("expiresAt"))
                or _as_opt_num(_read_env(env_vars, _ACCESS_TOKEN_EXPIRES_AT_KEYS))
            ),
        ),
        auth=AuthConfig(
            provider="google-oauth",
            client_id=_as_opt_str(auth_raw.get("clientId")),
            client_secret=_as_opt_str(auth_raw.get("clientSecret")),
            token_path=_as_opt_str(auth_raw.get("tokenPath")),
        ),
    )
    return Ok(cfg)
