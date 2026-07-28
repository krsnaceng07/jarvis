"""Media understanding provider surface (plugin SDK).

Mirrors OpenClaw's ``src/plugin-sdk/media-understanding.ts``,
specifically the ``transcribeOpenAiCompatibleAudio`` helper +
the ``MediaUnderstandingProvider`` descriptor type.

The Python port uses ``httpx`` (already a dep) for the actual
HTTP call to the OpenAI-compatible audio transcription API.
Provider-specific behavior (e.g. senseaudio's default
base URL + default model) lives in the individual extension
plugin modules; the SDK just provides the generic
``transcribe_openai_compatible_audio`` function.
"""
from __future__ import annotations

import base64
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class AudioTranscriptionRequest:
    """Input to ``transcribe_openai_compatible_audio``.

    Mirrors OpenClaw's ``AudioTranscriptionRequest``. The
    Python port adds a few convenience fields
    (``audio_base64``, ``audio_url``) for the two common
    ways to ship audio bytes to the API.
    """

    provider: str
    default_base_url: str
    default_model: str
    # Optional: one of ``audio_base64`` (raw bytes encoded
    # base64) or ``audio_url`` (remote URL) must be set.
    audio_base64: Optional[str] = None
    audio_url: Optional[str] = None
    audio_mime_type: str = "audio/wav"
    model: Optional[str] = None
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    language: Optional[str] = None
    prompt: Optional[str] = None
    temperature: Optional[float] = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AudioTranscriptionResult:
    """Result from ``transcribe_openai_compatible_audio``.

    Mirrors OpenClaw's ``AudioTranscriptionResult`` — at
    minimum a ``text`` field with the transcription.
    """

    text: str
    language: Optional[str] = None
    model: Optional[str] = None
    provider: Optional[str] = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class MediaUnderstandingProvider:
    """Descriptor for a media-understanding provider.

    Mirrors OpenClaw's ``MediaUnderstandingProvider``:
    a provider advertises the modalities it supports
    (audio/image/video) and the default models + priority
    for each. The ``transcribe_audio`` callable is invoked
    by the host when audio needs to be transcribed via this
    provider.

    The Python port keeps the same shape (id, label,
    capabilities, default_models, auto_priority,
    transcribe_audio) so plugins port same-to-same.
    """

    id: str
    capabilities: list[str] = field(default_factory=list)
    default_models: dict[str, str] = field(default_factory=dict)
    auto_priority: dict[str, int] = field(default_factory=dict)
    transcribe_audio: Any = None
    metadata: dict[str, Any] = field(default_factory=dict)


async def transcribe_openai_compatible_audio(
    params: AudioTranscriptionRequest,
) -> AudioTranscriptionResult:
    """Transcribe audio via an OpenAI-compatible audio API.

    Mirrors ``transcribeOpenAiCompatibleAudio`` in OpenClaw's
    ``src/media-understanding/openai-compatible-audio.js``.
    The Python port uses ``httpx.AsyncClient`` for the
    request — same call shape (POST ``/audio/transcriptions``,
    multipart form with the audio file + model).

    On error, returns a result with empty text + the
    error message in the ``raw`` field. The TS source
    throws; the Python port returns a degraded result
    so callers can decide whether to retry.
    """
    import httpx

    base_url = (params.base_url or params.default_base_url).rstrip("/")
    model = params.model or params.default_model

    if not params.api_key:
        return AudioTranscriptionResult(
            text="",
            model=model,
            provider=params.provider,
            raw={"error": f"missing api_key for {params.provider}"},
        )

    try:
        # Build the multipart form data
        form: dict[str, Any] = {
            "model": model,
        }
        if params.language:
            form["language"] = params.language
        if params.prompt:
            form["prompt"] = params.prompt
        if params.temperature is not None:
            form["temperature"] = str(params.temperature)

        if params.audio_base64:
            audio_bytes = base64.b64decode(params.audio_base64)
            files = {
                "file": (
                    "audio." + params.audio_mime_type.split("/")[-1],
                    audio_bytes,
                    params.audio_mime_type,
                ),
            }
        elif params.audio_url:
            # OpenAI-compatible APIs that accept URL inputs
            # (rare but the TS source supports it).
            form["url"] = params.audio_url
            files = None
        else:
            return AudioTranscriptionResult(
                text="",
                model=model,
                provider=params.provider,
                raw={"error": "no audio input (audio_base64 or audio_url required)"},
            )

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{base_url}/audio/transcriptions",
                headers={"Authorization": f"Bearer {params.api_key}"},
                data=form,
                files=files,
            )
            response.raise_for_status()
            payload = response.json()

        return AudioTranscriptionResult(
            text=str(payload.get("text", "")),
            language=payload.get("language"),
            model=payload.get("model", model),
            provider=params.provider,
            raw=payload,
        )
    except Exception as exc:  # noqa: BLE001 — best-effort transcription
        LOGGER.warning(
            "transcribe_openai_compatible_audio: %s transcription failed: %s",
            params.provider,
            exc,
        )
        return AudioTranscriptionResult(
            text="",
            model=model,
            provider=params.provider,
            raw={"error": str(exc)},
        )


__all__ = [
    "AudioTranscriptionRequest",
    "AudioTranscriptionResult",
    "MediaUnderstandingProvider",
    "transcribe_openai_compatible_audio",
]
