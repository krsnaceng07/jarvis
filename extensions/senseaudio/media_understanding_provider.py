"""SenseAudio media-understanding provider.

Mirrors OpenClaw's ``extensions/senseaudio/media-understanding-provider.ts``:
a thin descriptor wrapping the generic
``transcribe_openai_compatible_audio`` SDK function with
SenseAudio's default base URL + model.

Public surface:
- ``DEFAULT_SENSEAUDIO_AUDIO_BASE_URL`` — ``https://api.senseaudio.cn/v1``
- ``DEFAULT_SENSEAUDIO_AUDIO_MODEL`` — ``senseaudio-asr-pro-1.5-260319``
- ``transcribe_senseaudio_audio(params)`` — the async function
  the SDK calls to transcribe audio via SenseAudio
- ``senseaudio_media_understanding_provider`` — the
  ``MediaUnderstandingProvider`` descriptor the host reads
"""

from __future__ import annotations


from jarvis_sdk import (
    AudioTranscriptionRequest,
    AudioTranscriptionResult,
    MediaUnderstandingProvider,
    transcribe_openai_compatible_audio,
)

DEFAULT_SENSEAUDIO_AUDIO_BASE_URL = "https://api.senseaudio.cn/v1"
DEFAULT_SENSEAUDIO_AUDIO_MODEL = "senseaudio-asr-pro-1.5-260319"


async def transcribe_senseaudio_audio(
    params: AudioTranscriptionRequest,
) -> AudioTranscriptionResult:
    """Transcribe audio via the SenseAudio API.

    Wraps ``transcribe_openai_compatible_audio`` with
    SenseAudio's default base URL + model. Mirrors
    ``transcribeSenseAudioAudio`` in OpenClaw's
    ``extensions/senseaudio/media-understanding-provider.ts``.
    """
    return await transcribe_openai_compatible_audio(
        AudioTranscriptionRequest(
            provider="senseaudio",
            default_base_url=DEFAULT_SENSEAUDIO_AUDIO_BASE_URL,
            default_model=DEFAULT_SENSEAUDIO_AUDIO_MODEL,
            audio_base64=params.audio_base64,
            audio_url=params.audio_url,
            audio_mime_type=params.audio_mime_type,
            model=params.model,
            base_url=params.base_url,
            api_key=params.api_key,
            language=params.language,
            prompt=params.prompt,
            temperature=params.temperature,
            metadata=dict(params.metadata),
        )
    )


senseaudio_media_understanding_provider = MediaUnderstandingProvider(
    id="senseaudio",
    capabilities=["audio"],
    default_models={"audio": DEFAULT_SENSEAUDIO_AUDIO_MODEL},
    auto_priority={"audio": 40},
    transcribe_audio=transcribe_senseaudio_audio,
    metadata={"source": "openclaw-port"},
)


__all__ = [
    "DEFAULT_SENSEAUDIO_AUDIO_BASE_URL",
    "DEFAULT_SENSEAUDIO_AUDIO_MODEL",
    "senseaudio_media_understanding_provider",
    "transcribe_senseaudio_audio",
]
