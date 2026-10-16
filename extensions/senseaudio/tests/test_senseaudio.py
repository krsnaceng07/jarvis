"""Tests for the SenseAudio media-understanding provider port.

Mirrors OpenClaw's ``extensions/senseaudio`` (no dedicated
test file in the OpenClaw source — the surface is covered
indirectly by ``openai-compatible-audio.test.ts``). The
Python port tests the descriptor shape + the transcribe
function with a mocked HTTP transport.
"""

from __future__ import annotations

import asyncio
from unittest import mock

import pytest

from extensions.senseaudio import (
    DEFAULT_SENSEAUDIO_AUDIO_BASE_URL,
    DEFAULT_SENSEAUDIO_AUDIO_MODEL,
    senseaudio_media_understanding_provider,
    transcribe_senseaudio_audio,
)
from jarvis_sdk import (
    AudioTranscriptionRequest,
    PluginApi,
)
from jarvis_sdk.context import PluginContext


class TestSenseAudioProviderDescriptor:
    def test_descriptor_shape(self) -> None:
        """The provider descriptor carries the OpenClaw-shaped fields."""
        provider = senseaudio_media_understanding_provider
        assert provider.id == "senseaudio"
        assert "audio" in provider.capabilities
        assert provider.default_models.get("audio") == DEFAULT_SENSEAUDIO_AUDIO_MODEL
        assert provider.auto_priority.get("audio") == 40
        assert callable(provider.transcribe_audio)

    def test_default_base_url(self) -> None:
        assert DEFAULT_SENSEAUDIO_AUDIO_BASE_URL == "https://api.senseaudio.cn/v1"

    def test_default_model(self) -> None:
        assert DEFAULT_SENSEAUDIO_AUDIO_MODEL == "senseaudio-asr-pro-1.5-260319"


class TestSenseAudioPluginEntry:
    def test_plugin_registers_provider(self) -> None:
        """``register(api)`` adds the provider to ``api.media_understanding_providers``."""
        from extensions.senseaudio import senseaudio_plugin

        api = PluginApi(ctx=PluginContext(plugin_id="senseaudio", plugin_kind="infra"))
        senseaudio_plugin.register(api)
        providers = api.media_understanding_providers
        assert len(providers) == 1
        assert providers[0]["id"] == "senseaudio"
        assert "audio" in providers[0]["capabilities"]

    def test_plugin_id_and_kind(self) -> None:
        from extensions.senseaudio import senseaudio_plugin

        assert senseaudio_plugin.id == "senseaudio"
        assert senseaudio_plugin.kind == "infra"


class TestTranscribeSenseAudioAudio:
    def test_missing_api_key_returns_empty_text(self) -> None:
        """Without an ``api_key`` the helper returns empty text + an error."""
        request = AudioTranscriptionRequest(
            provider="senseaudio",
            default_base_url=DEFAULT_SENSEAUDIO_AUDIO_BASE_URL,
            default_model=DEFAULT_SENSEAUDIO_AUDIO_MODEL,
            audio_base64="ZmFrZQ==",  # "fake"
        )
        # Patch api_key to None
        request = AudioTranscriptionRequest(
            provider=request.provider,
            default_base_url=request.default_base_url,
            default_model=request.default_model,
            audio_base64=request.audio_base64,
            api_key=None,
        )
        result = asyncio.run(transcribe_senseaudio_audio(request))
        assert result.text == ""
        assert "missing api_key" in result.raw.get("error", "")

    def test_passes_provider_defaults_to_sdk_call(self) -> None:
        """``transcribe_senseaudio_audio`` forwards senseaudio defaults + the request payload."""
        # Patch the SDK's transcribe function to capture the call
        with mock.patch(
            "extensions.senseaudio.media_understanding_provider.transcribe_openai_compatible_audio"
        ) as mock_transcribe:

            async def fake_transcribe(params):
                from jarvis_sdk import AudioTranscriptionResult

                return AudioTranscriptionResult(
                    text="hello world",
                    model=params.model or params.default_model,
                    provider=params.provider,
                )

            mock_transcribe.side_effect = fake_transcribe

            request = AudioTranscriptionRequest(
                provider="caller",
                default_base_url="https://override.example/v1",
                default_model="override-model",
                audio_base64="aGVsbG8=",
                model="caller-model",
                api_key="sk-test",
            )
            result = asyncio.run(transcribe_senseaudio_audio(request))
            # Verify the SDK call was made with senseaudio defaults.
            call_args = mock_transcribe.call_args
            forwarded: AudioTranscriptionRequest = call_args.args[0]
            assert forwarded.provider == "senseaudio"
            assert forwarded.default_base_url == DEFAULT_SENSEAUDIO_AUDIO_BASE_URL
            assert forwarded.default_model == DEFAULT_SENSEAUDIO_AUDIO_MODEL
            assert forwarded.audio_base64 == "aGVsbG8="
            assert forwarded.model == "caller-model"
            assert forwarded.api_key == "sk-test"
            # Result is from the fake
            assert result.text == "hello world"

    def test_passes_no_audio_input(self) -> None:
        """No audio_base64 or audio_url → error in result."""
        request = AudioTranscriptionRequest(
            provider="senseaudio",
            default_base_url=DEFAULT_SENSEAUDIO_AUDIO_BASE_URL,
            default_model=DEFAULT_SENSEAUDIO_AUDIO_MODEL,
            api_key="sk-test",
        )
        result = asyncio.run(transcribe_senseaudio_audio(request))
        assert result.text == ""
        assert "audio" in result.raw.get("error", "").lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
