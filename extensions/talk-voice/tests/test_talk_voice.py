"""Tests for talk-voice command and plugin."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock
import pytest

from extensions.talk_voice.src.voice_command import (
    SpeechVoiceOption,
    handle_voice_command,
)


class MockContext:
    def __init__(
        self,
        args: str = "",
        channel: str = "discord",
        gateway_client_scopes: list[str] | None = None,
        sender_is_owner: bool | None = None,
    ) -> None:
        self.args = args
        self.channel = channel
        self.gateway_client_scopes = gateway_client_scopes
        self.sender_is_owner = sender_is_owner


class MockRuntime:
    def __init__(self, initial_config: dict[str, Any]) -> None:
        self._config = initial_config
        self.config = MagicMock()
        self.config.current = MagicMock(side_effect=lambda: self._config)
        self.config.mutate_config_file = AsyncMock(side_effect=self._mutate)
        self.tts = MagicMock()
        self.tts.list_voices = AsyncMock()

    async def _mutate(self, mutate: Any, after_write: Any = None) -> None:
        import copy

        draft = copy.deepcopy(self._config)
        await mutate(draft)
        self._config = draft


@pytest.mark.asyncio
async def test_reports_active_provider_status() -> None:
    runtime = MockRuntime(
        {
            "talk": {
                "provider": "microsoft",
                "providers": {
                    "microsoft": {
                        "voiceId": "en-US-AvaNeural",
                        "apiKey": "secret-token",
                    }
                },
            }
        }
    )
    ctx = MockContext(args="")
    result = await handle_voice_command(ctx, runtime)
    assert result == {
        "text": (
            "Talk voice status:\n"
            "- provider: microsoft\n"
            "- talk.providers.microsoft.voiceId: en-US-AvaNeural\n"
            "- microsoft.apiKey: secret…"
        )
    }


@pytest.mark.asyncio
async def test_lists_voices_from_active_provider() -> None:
    runtime = MockRuntime(
        {
            "talk": {
                "provider": "elevenlabs",
                "providers": {
                    "elevenlabs": {
                        "apiKey": "sk-eleven",
                        "baseUrl": "https://voices.example.test",
                    }
                },
            }
        }
    )
    runtime.tts.list_voices.return_value = [
        SpeechVoiceOption(id="voice-a", name="Claudia", category="general"),
        SpeechVoiceOption(id="voice-b", name="Bert"),
    ]

    ctx = MockContext(args="list +01")
    result = await handle_voice_command(ctx, runtime)

    runtime.tts.list_voices.assert_awaited_once_with(
        provider="elevenlabs",
        cfg={
            "talk": {
                "provider": "elevenlabs",
                "providers": {
                    "elevenlabs": {
                        "apiKey": "sk-eleven",
                        "baseUrl": "https://voices.example.test",
                    }
                },
            }
        },
        api_key="sk-eleven",
        base_url="https://voices.example.test",
    )
    assert result == {
        "text": ("ElevenLabs voices: 2\n\n- Claudia · general\n  id: voice-a\n\n(showing first 1)")
    }


@pytest.mark.asyncio
async def test_does_not_coerce_partial_voice_list_limits() -> None:
    runtime = MockRuntime(
        {
            "talk": {
                "provider": "elevenlabs",
                "providers": {"elevenlabs": {"apiKey": "sk-eleven"}},
            }
        }
    )
    runtime.tts.list_voices.return_value = [
        SpeechVoiceOption(id=f"voice-{i}", name=f"Voice {i}") for i in range(13)
    ]

    ctx = MockContext(args="list 1x")
    result = await handle_voice_command(ctx, runtime)
    assert "(showing first 12)" in result["text"]


@pytest.mark.asyncio
async def test_surfaces_richer_provider_voice_metadata() -> None:
    runtime = MockRuntime(
        {
            "talk": {
                "provider": "microsoft",
                "providers": {"microsoft": {}},
            }
        }
    )
    runtime.tts.list_voices.return_value = [
        SpeechVoiceOption(
            id="en-US-AvaNeural",
            name="Ava",
            category="General",
            locale="en-US",
            gender="Female",
            personalities=["Friendly", "Positive"],
            description="Friendly, Positive",
        )
    ]

    ctx = MockContext(args="list")
    result = await handle_voice_command(ctx, runtime)
    assert result == {
        "text": (
            "Microsoft voices: 1\n\n"
            "- Ava · General\n"
            "  id: en-US-AvaNeural\n"
            "  meta: en-US · Female · Friendly, Positive\n"
            "  note: Friendly, Positive"
        )
    }


@pytest.mark.asyncio
async def test_writes_canonical_provider_scoped_voice_config_for_elevenlabs() -> None:
    runtime = MockRuntime(
        {
            "talk": {
                "provider": "elevenlabs",
                "providers": {
                    "elevenlabs": {"apiKey": "sk-eleven"},
                },
            }
        }
    )
    runtime.tts.list_voices.return_value = [
        SpeechVoiceOption(id="voice-a", name="Claudia"),
    ]

    ctx = MockContext(
        args="set Claudia", channel="webchat", gateway_client_scopes=["operator.admin"]
    )
    result = await handle_voice_command(ctx, runtime)

    runtime.config.mutate_config_file.assert_awaited_once()
    assert runtime._config == {
        "talk": {
            "provider": "elevenlabs",
            "providers": {
                "elevenlabs": {
                    "apiKey": "sk-eleven",
                    "voiceId": "voice-a",
                }
            },
        }
    }
    assert result == {
        "text": "✅ ElevenLabs Talk voice set to Claudia\nvoice-a",
    }


@pytest.mark.asyncio
async def test_writes_provider_voice_id_without_top_level_field_for_microsoft() -> None:
    runtime = MockRuntime(
        {
            "talk": {
                "provider": "microsoft",
                "providers": {"microsoft": {}},
            }
        }
    )
    runtime.tts.list_voices.return_value = [
        SpeechVoiceOption(id="en-US-AvaNeural", name="Ava"),
    ]

    ctx = MockContext(args="set Ava", channel="webchat", gateway_client_scopes=["operator.admin"])
    await handle_voice_command(ctx, runtime)

    runtime.config.mutate_config_file.assert_awaited_once()
    assert runtime._config == {
        "talk": {
            "provider": "microsoft",
            "providers": {
                "microsoft": {
                    "voiceId": "en-US-AvaNeural",
                }
            },
        }
    }


@pytest.mark.asyncio
async def test_rejects_set_from_gateway_client_with_only_write_scope() -> None:
    runtime = MockRuntime(
        {
            "talk": {
                "provider": "elevenlabs",
                "providers": {"elevenlabs": {"apiKey": "sk-eleven"}},
            }
        }
    )
    runtime.tts.list_voices.return_value = [
        SpeechVoiceOption(id="voice-a", name="Claudia"),
    ]

    ctx = MockContext(
        args="set Claudia", channel="webchat", gateway_client_scopes=["operator.write"]
    )
    result = await handle_voice_command(ctx, runtime)
    assert "requires operator.admin" in result["text"]
    runtime.config.mutate_config_file.assert_not_awaited()


@pytest.mark.asyncio
async def test_rejects_set_from_non_webchat_callers_missing_admin() -> None:
    runtime = MockRuntime(
        {
            "talk": {
                "provider": "elevenlabs",
                "providers": {"elevenlabs": {"apiKey": "sk-eleven"}},
            }
        }
    )
    runtime.tts.list_voices.return_value = [
        SpeechVoiceOption(id="voice-a", name="Claudia"),
    ]

    ctx = MockContext(
        args="set Claudia", channel="telegram", gateway_client_scopes=["operator.write"]
    )
    result = await handle_voice_command(ctx, runtime)
    assert "requires operator.admin" in result["text"]
    runtime.config.mutate_config_file.assert_not_awaited()


@pytest.mark.asyncio
async def test_allows_set_when_admin_present() -> None:
    runtime = MockRuntime(
        {
            "talk": {
                "provider": "elevenlabs",
                "providers": {"elevenlabs": {"apiKey": "sk-eleven"}},
            }
        }
    )
    runtime.tts.list_voices.return_value = [
        SpeechVoiceOption(id="voice-a", name="Claudia"),
    ]

    ctx = MockContext(
        args="set Claudia", channel="telegram", gateway_client_scopes=["operator.admin"]
    )
    result = await handle_voice_command(ctx, runtime)
    assert "voice-a" in result["text"]
    runtime.config.mutate_config_file.assert_awaited()


@pytest.mark.asyncio
async def test_allows_set_from_owner_channel_without_scopes() -> None:
    runtime = MockRuntime(
        {
            "talk": {
                "provider": "elevenlabs",
                "providers": {"elevenlabs": {"apiKey": "sk-eleven"}},
            }
        }
    )
    runtime.tts.list_voices.return_value = [
        SpeechVoiceOption(id="voice-a", name="Claudia"),
    ]

    ctx = MockContext(args="set Claudia", channel="telegram", sender_is_owner=True)
    result = await handle_voice_command(ctx, runtime)
    assert "voice-a" in result["text"]
    runtime.config.mutate_config_file.assert_awaited()


@pytest.mark.asyncio
async def test_keeps_read_only_voice_commands_available_without_admin() -> None:
    runtime = MockRuntime(
        {
            "talk": {
                "provider": "elevenlabs",
                "providers": {"elevenlabs": {"apiKey": "sk-eleven"}},
            }
        }
    )
    runtime.tts.list_voices.return_value = [
        SpeechVoiceOption(id="voice-a", name="Claudia"),
    ]

    status = await handle_voice_command(MockContext(args="status", channel="telegram"), runtime)
    list_res = await handle_voice_command(MockContext(args="list", channel="telegram"), runtime)

    assert "Talk voice status:" in status["text"]
    assert "ElevenLabs voices: 1" in list_res["text"]
    runtime.config.mutate_config_file.assert_not_awaited()


@pytest.mark.asyncio
async def test_returns_provider_lookup_errors_cleanly() -> None:
    runtime = MockRuntime(
        {
            "talk": {
                "provider": "microsoft",
                "providers": {"microsoft": {}},
            }
        }
    )
    runtime.tts.list_voices.side_effect = RuntimeError(
        "speech provider microsoft does not support voice listing"
    )

    result = await handle_voice_command(MockContext(args="list"), runtime)
    assert result == {
        "text": "Microsoft voice list failed: speech provider microsoft does not support voice listing"
    }
