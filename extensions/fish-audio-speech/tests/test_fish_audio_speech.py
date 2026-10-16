"""Unit tests for fish-audio-speech provider."""

import asyncio
from unittest import mock
import pytest

from extensions.fish_audio_speech.src.speech_provider import (
    build_fish_audio_speech_provider,
    normalize_latency,
    normalize_model,
    normalize_provider_config,
)
from extensions.fish_audio_speech.src.tts import (
    build_fish_audio_request_body,
    normalize_fish_audio_base_url,
    parse_voice_item,
)


def test_normalize_model() -> None:
    assert normalize_model("s2.1-pro") == "s2.1-pro"
    assert normalize_model("s1") == "s1"
    assert normalize_model(None) == "s2.1-pro"
    with pytest.raises(ValueError, match="invalid Fish Audio model"):
        normalize_model("invalid-model")


def test_normalize_latency() -> None:
    assert normalize_latency("low") == "low"
    assert normalize_latency("BALANCED") == "balanced"
    assert normalize_latency(None) == "balanced"
    with pytest.raises(ValueError, match="invalid Fish Audio latency"):
        normalize_latency("super-fast")


def test_normalize_base_url() -> None:
    assert normalize_fish_audio_base_url(None) == "https://api.fish.audio"
    assert normalize_fish_audio_base_url("https://custom.api.fish///") == "https://custom.api.fish"


def test_normalize_provider_config(sample_fish_config: dict[str, dict[str, dict[str, str | float]]]) -> None:
    cfg = normalize_provider_config(sample_fish_config)
    assert cfg["apiKey"] == "test-key-123"
    assert cfg["model"] == "s2.1-pro"
    assert cfg["latency"] == "low"
    assert cfg["speed"] == 1.2


def test_build_request_body() -> None:
    body = build_fish_audio_request_body(
        {
            "text": "Hello world",
            "format": "mp3",
            "referenceId": "ref-1",
            "speed": 1.1,
        }
    )
    import json

    parsed = json.loads(body)
    assert parsed["text"] == "Hello world"
    assert parsed["format"] == "mp3"
    assert parsed["reference_id"] == "ref-1"
    assert parsed["prosody"]["speed"] == 1.1


def test_parse_voice_item() -> None:
    raw = {
        "_id": "voice_123",
        "title": "Friendly Speaker",
        "description": "Warm voice",
        "visibility": "public",
        "languages": ["en", "zh"],
        "tags": ["friendly", "warm"],
    }
    voice = parse_voice_item(raw)
    assert voice is not None
    assert voice["id"] == "voice_123"
    assert voice["name"] == "Friendly Speaker"
    assert voice["locale"] == "en"
    assert voice["personalities"] == ["friendly", "warm"]


def test_speech_provider_synthesize(sample_fish_config: dict[str, dict[str, dict[str, str | float]]]) -> None:
    provider = build_fish_audio_speech_provider()
    assert provider.id == "fish-audio"
    assert provider.is_configured(sample_fish_config)

    with mock.patch("extensions.fish_audio_speech.src.speech_provider.fish_audio_tts") as mock_tts:
        mock_tts.return_value = b"RIFF-mock-audio-data"
        result = asyncio.run(
            provider.synthesize(
                {
                    "text": "Testing synthesis",
                    "providerConfig": sample_fish_config,
                    "target": "voice-note",
                }
            )
        )
        assert result["outputFormat"] == "opus"
        assert result["fileExtension"] == ".opus"
        assert result["voiceCompatible"] is True
        assert result["audioBuffer"] == b"RIFF-mock-audio-data"
