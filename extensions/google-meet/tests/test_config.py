"""Tests for Google Meet configuration resolution, normalization, compatibility, and vendor profiles."""

from extensions.google_meet.src.config import (
    DEFAULT_GOOGLE_MEET_BARGE_IN_COOLDOWN_MS,
    DEFAULT_GOOGLE_MEET_BARGE_IN_PEAK_THRESHOLD,
    DEFAULT_GOOGLE_MEET_BARGE_IN_RMS_THRESHOLD,
    DEFAULT_GOOGLE_MEET_REALTIME_INTRO_MESSAGE,
    resolve_google_meet_config,
)
from extensions.google_meet.src.config_compat import (
    migrate_google_meet_legacy_realtime_provider,
    migrate_legacy_google_meet_config,
)


def test_migrate_legacy_google_meet_config():
    legacy = {
        "chromeProfile": "Default",
        "audioIn": "Microphone 1",
        "audioOut": "Speakers 1",
        "clientId": "client-123",
        "clientSecret": "secret-456",
        "accessToken": "token-789",
    }
    migrated, changed = migrate_legacy_google_meet_config(legacy)
    assert changed
    assert migrated["chrome"]["profile"] == "Default"
    assert migrated["chrome"]["audioIn"] == "Microphone 1"
    assert migrated["chrome"]["audioOut"] == "Speakers 1"
    assert migrated["oauth"]["clientId"] == "client-123"
    assert migrated["oauth"]["clientSecret"] == "secret-456"
    assert migrated["oauth"]["accessToken"] == "token-789"


def test_migrate_legacy_google_realtime_provider():
    cfg = {
        "plugins": {
            "entries": {
                "google-meet": {
                    "enabled": True,
                    "config": {
                        "realtime": {
                            "provider": "google",
                        }
                    },
                }
            }
        }
    }
    migrated = migrate_google_meet_legacy_realtime_provider(cfg)
    assert migrated is not None
    rt = migrated["plugins"]["entries"]["google-meet"]["config"]["realtime"]
    assert rt["provider"] == "openai"
    assert rt["voiceProvider"] == "google"
    assert rt["transcriptionProvider"] == "openai"


def test_resolve_google_meet_config_defaults():
    res = resolve_google_meet_config({})
    assert res.is_ok
    cfg = res.unwrap()

    # Defaults table verification
    assert cfg.default_transport == "chrome"
    assert cfg.default_mode == "agent"
    assert cfg.chrome_node.node is None

    # Chrome defaults
    assert cfg.chrome.launch is True
    assert cfg.chrome.audio_backend == "auto"
    assert cfg.chrome.auto_join is True
    assert cfg.chrome.reuse_existing_tab is True
    assert cfg.chrome.wait_for_in_call_ms == 20000
    assert cfg.chrome.audio_format == "pcm16-24khz"
    assert cfg.chrome.audio_buffer_bytes == 4096
    assert cfg.chrome.barge_in_input_command is None
    assert cfg.chrome.barge_in_rms_threshold == DEFAULT_GOOGLE_MEET_BARGE_IN_RMS_THRESHOLD
    assert cfg.chrome.barge_in_peak_threshold == DEFAULT_GOOGLE_MEET_BARGE_IN_PEAK_THRESHOLD
    assert cfg.chrome.barge_in_cooldown_ms == DEFAULT_GOOGLE_MEET_BARGE_IN_COOLDOWN_MS

    # Realtime defaults
    assert cfg.realtime.provider == "openai"
    assert cfg.realtime.transcription_provider == "openai"
    assert cfg.realtime.voice_provider is None
    assert cfg.realtime.tool_policy == "safe-read-only"
    assert cfg.realtime.intro_message == DEFAULT_GOOGLE_MEET_REALTIME_INTRO_MESSAGE

    # Voice call defaults
    assert cfg.voice_call.enabled is True
    assert cfg.voice_call.dtmf_delay_ms == 12000
    assert cfg.voice_call.post_dtmf_speech_delay_ms == 5000


def test_resolve_google_meet_config_with_oauth():
    raw = {
        "oauth": {
            "clientId": "test-client-id",
            "clientSecret": "test-client-secret",
            "accessToken": "test-access-token",
            "refreshToken": "test-refresh-token",
            "expiresAt": 1700000000,
        },
        "chrome": {
            "browserProfile": "WorkProfile",
        },
        "chromeNode": {
            "node": "node-alpha",
        },
    }
    res = resolve_google_meet_config(raw)
    assert res.is_ok
    cfg = res.unwrap()
    assert cfg.oauth is not None
    assert cfg.oauth.client_id == "test-client-id"
    assert cfg.oauth.client_secret == "test-client-secret"
    assert cfg.oauth.access_token == "test-access-token"
    assert cfg.chrome.browser_profile == "WorkProfile"
    assert cfg.chrome_node.node == "node-alpha"


def test_resolve_google_meet_optional_overrides_and_gemini_live():
    raw = {
        "defaults": {
            "meeting": "https://meet.google.com/abc-defg-hij",
        },
        "chrome": {
            "guestName": "JARVIS Agent",
            "waitForInCallMs": 30000,
            "bargeInInputCommand": [
                "sox",
                "-q",
                "-t",
                "coreaudio",
                "External Microphone",
                "-r",
                "24000",
                "-c",
                "1",
                "-b",
                "16",
                "-e",
                "signed-integer",
                "-t",
                "raw",
                "-",
            ],
        },
        "chromeNode": {
            "node": "parallels-macos",
        },
        "defaultMode": "agent",
        "realtime": {
            "provider": "openai",
            "transcriptionProvider": "openai",
            "voiceProvider": "google",
            "model": "gemini-3.1-flash-live-preview",
            "agentId": "jay",
            "toolPolicy": "owner",
            "introMessage": "Say exactly: I'm here.",
            "providers": {
                "google": {
                    "speakerVoice": "Kore",
                },
            },
        },
    }
    res = resolve_google_meet_config(raw)
    assert res.is_ok
    cfg = res.unwrap()
    assert cfg.defaults.meeting == "https://meet.google.com/abc-defg-hij"
    assert cfg.chrome.wait_for_in_call_ms == 30000
    assert cfg.chrome.barge_in_input_command is not None
    assert cfg.chrome.barge_in_input_command[0] == "sox"
    assert cfg.chrome_node.node == "parallels-macos"
    assert cfg.realtime.voice_provider == "google"
    assert cfg.realtime.model == "gemini-3.1-flash-live-preview"
    assert cfg.realtime.agent_id == "jay"
    assert cfg.realtime.tool_policy == "owner"
    assert cfg.realtime.intro_message == "Say exactly: I'm here."
    assert cfg.realtime.providers["google"]["speakerVoice"] == "Kore"


def test_resolve_google_meet_elevenlabs_profile():
    raw = {
        "realtime": {
            "transcriptionProvider": "elevenlabs",
            "providers": {
                "elevenlabs": {
                    "modelId": "scribe_v2_realtime",
                    "audioFormat": "ulaw_8000",
                    "sampleRate": 8000,
                    "commitStrategy": "vad",
                },
            },
        },
    }
    res = resolve_google_meet_config(raw)
    assert res.is_ok
    cfg = res.unwrap()
    assert cfg.realtime.transcription_provider == "elevenlabs"
    assert cfg.realtime.providers["elevenlabs"]["modelId"] == "scribe_v2_realtime"
    assert cfg.realtime.providers["elevenlabs"]["audioFormat"] == "ulaw_8000"
    assert cfg.realtime.providers["elevenlabs"]["sampleRate"] == 8000


def test_resolve_google_meet_twilio_only_config():
    raw = {
        "defaultTransport": "twilio",
        "twilio": {
            "defaultDialInNumber": "+15551234567",
            "defaultPin": "123456",
        },
        "voiceCall": {
            "gatewayUrl": "ws://127.0.0.1:18789",
        },
    }
    res = resolve_google_meet_config(raw)
    assert res.is_ok
    cfg = res.unwrap()
    assert cfg.default_transport == "twilio"
    assert cfg.twilio.default_dial_in_number == "+15551234567"
    assert cfg.twilio.default_pin == "123456"
    assert cfg.voice_call.gateway_url == "ws://127.0.0.1:18789"
    assert cfg.voice_call.enabled is True
