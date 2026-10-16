"""Speech provider plugin SDK types.

Mirrors OpenClaw's ``openclaw/plugin-sdk/speech-core``.

The speech provider is a long-running service the host
calls to synthesize audio from text. Multiple providers
can be registered; the host picks one per request based on
the request's ``providerId`` and the provider's
``defaultFor`` hint.

Public types (mirrors the TS source):
- ``SpeechProviderConfig`` — per-provider config dict
- ``SpeechProviderPlugin`` — the registered provider
  descriptor
- ``SpeechSynthesisRequest`` — the synthesis request
- ``SpeechTelephonySynthesisRequest`` — telephony-flavored
  request (extra telephony quality settings)

Public constants:
- ``VALID_SPEECH_OUTPUT_FORMATS`` = ``{"mp3", "opus", "wav"}``

Python adaptations (documented in code):
- TS string-literal unions → Python ``Literal[...]`` +
  ``frozenset`` membership sets
- TS ``async`` callable fields → Python
  ``Callable[..., Awaitable[Any]]`` signatures
- TS ``Buffer``/``Uint8Array`` audio bytes → Python
  ``bytes``
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Literal, TypedDict

# ── Public literal unions ─────────────────────────────────


SpeechOutputFormat = Literal["mp3", "opus", "wav"]
VALID_SPEECH_OUTPUT_FORMATS: frozenset[str] = frozenset({"mp3", "opus", "wav"})


# ── Type aliases ──────────────────────────────────────────


class SpeechProviderConfig(TypedDict, total=False):
    # Provider config is open-ended; the SDK does not enforce
    # a fixed shape. The provider module parses its own
    # keys.
    command: str
    args: list[str]
    outputFormat: SpeechOutputFormat
    timeoutMs: int
    cwd: str
    env: dict[str, str]


class SpeechSynthesisRequest(TypedDict, total=False):
    text: str
    voice: str
    outputFormat: SpeechOutputFormat
    providerId: str


class SpeechTelephonySynthesisRequest(SpeechSynthesisRequest, total=False):
    """Telephony-flavored synthesis request (extra quality settings)."""

    sampleRateHz: int
    telephonyQuality: Literal["narrowband", "wideband", "superwideband", "fullband"]


# The synthesized audio + metadata. The provider can return
# raw audio bytes or a path to a file the host should
# slurp.
class SpeechSynthesisResult(TypedDict, total=False):
    audio: bytes
    format: SpeechOutputFormat
    durationMs: int
    sourcePath: str


# Callable signatures. The host invokes the appropriate
# one based on the request shape.
SynthesizeFn = Callable[
    [SpeechSynthesisRequest, SpeechProviderConfig],
    Awaitable[SpeechSynthesisResult],
]
SynthesizeTelephonyFn = Callable[
    [SpeechTelephonySynthesisRequest, SpeechProviderConfig],
    Awaitable[SpeechSynthesisResult],
]
ListVoicesFn = Callable[
    [SpeechProviderConfig],
    Awaitable[list[dict[str, Any]]],
]


class SpeechProviderPlugin(TypedDict, total=False):
    id: str
    label: str
    description: str
    aliases: list[str]
    autoSelectOrder: int
    defaultTimeoutMs: int
    """Provider's preferred output format (host hint)."""
    defaultFormat: SpeechOutputFormat
    """Provider id this one is the default for (host hint)."""
    defaultFor: str
    synthesize: SynthesizeFn
    synthesizeTelephony: SynthesizeTelephonyFn
    listVoices: ListVoicesFn
    metadata: dict[str, Any]


__all__ = [
    "ListVoicesFn",
    "SpeechOutputFormat",
    "SpeechProviderConfig",
    "SpeechProviderPlugin",
    "SpeechSynthesisRequest",
    "SpeechSynthesisResult",
    "SpeechTelephonySynthesisRequest",
    "SynthesizeFn",
    "SynthesizeTelephonyFn",
    "VALID_SPEECH_OUTPUT_FORMATS",
]
