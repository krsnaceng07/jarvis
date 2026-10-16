"""Fish Audio provider maps OpenClaw / JARVIS speech contracts to the hosted S2.1 API.

OpenClaw parity: mirrors extensions/fish-audio-speech/speech-provider.ts.
"""

from __future__ import annotations

import os
from typing import Any, TypedDict

from .tts import (
    FISH_AUDIO_STREAM_MAX_BYTES,
    FishAudioLatency,
    FishAudioModel,
    fish_audio_tts,
    list_fish_audio_voices,
    normalize_fish_audio_base_url,
)

FISH_AUDIO_MODELS: list[FishAudioModel] = ["s2.1-pro-free", "s2.1-pro", "s2-pro", "s1"]
DEFAULT_MODEL: FishAudioModel = "s2.1-pro"
DEFAULT_LATENCY: FishAudioLatency = "balanced"
DEFAULT_TIMEOUT_MS = 240_000


class FishAudioProviderConfig(TypedDict, total=False):
    apiKey: str | None
    baseUrl: str
    model: FishAudioModel
    referenceId: str | None
    latency: FishAudioLatency
    speed: float | None
    temperature: float | None
    topP: float | None
    normalize: bool | None


class FishAudioOverrides(TypedDict, total=False):
    model: FishAudioModel | None
    referenceId: str | None
    latency: FishAudioLatency | None
    speed: float | None
    temperature: float | None
    topP: float | None
    normalize: bool | None


def normalize_model(value: Any) -> FishAudioModel:
    if not value or not isinstance(value, str) or not value.strip():
        return DEFAULT_MODEL
    trimmed = value.strip()
    if trimmed in FISH_AUDIO_MODELS:
        return trimmed  # type: ignore[return-value]
    raise ValueError(f'invalid Fish Audio model "{trimmed}"')


def normalize_latency(value: Any) -> FishAudioLatency:
    if not value or not isinstance(value, str) or not value.strip():
        return DEFAULT_LATENCY
    lat = value.strip().lower()
    if lat in ("low", "balanced", "normal"):
        return lat  # type: ignore[return-value]
    raise ValueError(f'invalid Fish Audio latency "{lat}"')


def normalize_number(value: Any, min_val: float, max_val: float) -> float | None:
    if value is None:
        return None
    try:
        num = float(value)
        if min_val <= num <= max_val:
            return num
    except (ValueError, TypeError):
        pass
    return None


def resolve_reference_id(raw: dict[str, Any] | None) -> str | None:
    if not isinstance(raw, dict):
        return None
    for key in ("speakerVoiceId", "voiceId", "referenceId", "voice_id", "reference_id"):
        val = raw.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return None


def normalize_provider_config(raw_config: dict[str, Any] | None) -> FishAudioProviderConfig:
    raw_dict = raw_config if isinstance(raw_config, dict) else {}
    providers = raw_dict.get("providers") if isinstance(raw_dict.get("providers"), dict) else {}
    raw = providers.get("fish-audio") or raw_dict.get("fish-audio") or raw_dict

    api_key = raw.get("apiKey") if isinstance(raw.get("apiKey"), str) else None
    base_url = normalize_fish_audio_base_url(
        raw.get("baseUrl") if isinstance(raw.get("baseUrl"), str) else None
    )
    model_val = raw.get("model") or raw.get("modelId")
    model = normalize_model(model_val) if model_val else DEFAULT_MODEL

    return {
        "apiKey": api_key.strip() if api_key and api_key.strip() else None,
        "baseUrl": base_url,
        "model": model,
        "referenceId": resolve_reference_id(raw),
        "latency": normalize_latency(raw.get("latency")),
        "speed": normalize_number(raw.get("speed"), 0.5, 2.0),
        "temperature": normalize_number(raw.get("temperature"), 0.0, 1.0),
        "topP": normalize_number(raw.get("topP") or raw.get("top_p"), 0.0, 1.0),
        "normalize": bool(raw.get("normalize")) if "normalize" in raw else None,
    }


def resolve_api_key(config_value: str | None = None) -> str | None:
    if config_value and config_value.strip():
        return config_value.strip()
    return os.environ.get("FISH_API_KEY") or os.environ.get("FISH_AUDIO_API_KEY") or None


def resolve_format(target: str) -> dict[str, Any]:
    if target == "voice-note":
        return {
            "format": "opus",
            "sampleRate": 48_000,
            "fileExtension": ".opus",
            "voiceCompatible": True,
        }
    if target == "telephony":
        return {
            "format": "pcm",
            "sampleRate": 8_000,
            "fileExtension": ".pcm",
            "voiceCompatible": False,
        }
    return {
        "format": "mp3",
        "sampleRate": 44_100,
        "fileExtension": ".mp3",
        "voiceCompatible": False,
    }


class FishAudioSpeechProvider:
    id = "fish-audio"
    label = "Fish Audio"
    auto_select_order = 28
    default_timeout_ms = DEFAULT_TIMEOUT_MS
    default_model = DEFAULT_MODEL
    models = FISH_AUDIO_MODELS

    def resolve_config(self, raw_config: dict[str, Any]) -> FishAudioProviderConfig:
        return normalize_provider_config(raw_config)

    def is_configured(self, provider_config: dict[str, Any]) -> bool:
        cfg = normalize_provider_config(provider_config)
        return resolve_api_key(cfg.get("apiKey")) is not None

    async def list_voices(self, req: dict[str, Any]) -> list[dict[str, Any]]:
        cfg = normalize_provider_config(req.get("providerConfig"))
        api_key = resolve_api_key(req.get("apiKey") or cfg.get("apiKey"))
        if not api_key:
            raise ValueError("Fish Audio API key missing")
        return await list_fish_audio_voices(
            {
                "apiKey": api_key,
                "baseUrl": req.get("baseUrl") or cfg.get("baseUrl"),
                "timeoutMs": req.get("timeoutMs", DEFAULT_TIMEOUT_MS),
            }
        )  # type: ignore[return-value]

    async def synthesize(self, req: dict[str, Any]) -> dict[str, Any]:
        cfg = normalize_provider_config(req.get("providerConfig"))
        overrides = req.get("providerOverrides", {})
        api_key = resolve_api_key(cfg.get("apiKey"))
        if not api_key:
            raise ValueError("Fish Audio API key missing")
        target = req.get("target", "default")
        out_fmt = resolve_format(target)
        tts_req = {
            "text": req.get("text", ""),
            "apiKey": api_key,
            "baseUrl": cfg.get("baseUrl"),
            "model": overrides.get("model") or cfg.get("model", DEFAULT_MODEL),
            "referenceId": overrides.get("referenceId") or cfg.get("referenceId"),
            "latency": overrides.get("latency") or cfg.get("latency", DEFAULT_LATENCY),
            "speed": overrides.get("speed")
            if overrides.get("speed") is not None
            else cfg.get("speed"),
            "temperature": overrides.get("temperature")
            if overrides.get("temperature") is not None
            else cfg.get("temperature"),
            "topP": overrides.get("topP") if overrides.get("topP") is not None else cfg.get("topP"),
            "normalize": overrides.get("normalize")
            if overrides.get("normalize") is not None
            else cfg.get("normalize"),
            "timeoutMs": req.get("timeoutMs", DEFAULT_TIMEOUT_MS),
            "maxBytes": req.get("maxBytes", FISH_AUDIO_STREAM_MAX_BYTES),
            **out_fmt,
        }
        audio_bytes = await fish_audio_tts(tts_req)
        return {
            "audioBuffer": audio_bytes,
            "outputFormat": out_fmt["format"],
            "fileExtension": out_fmt["fileExtension"],
            "voiceCompatible": out_fmt["voiceCompatible"],
        }

    async def synthesize_telephony(self, req: dict[str, Any]) -> dict[str, Any]:
        res = await self.synthesize({**req, "target": "telephony"})
        return {
            "audioBuffer": res["audioBuffer"],
            "outputFormat": "pcm",
            "sampleRate": 8_000,
        }


def build_fish_audio_speech_provider() -> FishAudioSpeechProvider:
    return FishAudioSpeechProvider()
