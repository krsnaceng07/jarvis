"""Text-to-speech synthesis and telephony audio formatting for Voice Call."""

from __future__ import annotations

import asyncio
import logging
import struct
from dataclasses import dataclass
from typing import Any


from ..config import VoiceCallConfig, VoiceCallTTSConfig

logger = logging.getLogger(__name__)

try:
    import audioop
except ImportError:
    audioop = None  # type: ignore[assignment]


def _pcm16_to_ulaw(pcm_data: bytes) -> bytes:
    """Pure-Python fallback for linear PCM 16-bit to G.711 μ-law conversion."""
    if audioop is not None:
        try:
            return audioop.lin2ulaw(pcm_data, 2)
        except Exception:
            pass

    out = bytearray()
    count = len(pcm_data) // 2
    samples = struct.unpack(f"<{count}h", pcm_data[: count * 2])
    bias = 0x84
    clip = 32635

    for sample in samples:
        sign = 0x80 if sample < 0 else 0
        if sample < 0:
            sample = -sample
        if sample > clip:
            sample = clip
        sample += bias
        exponent = 7
        for exp, mask in enumerate((0x4000, 0x2000, 0x1000, 0x0800, 0x0400, 0x0200, 0x0100)):
            if sample & mask:
                exponent = 7 - exp
                break
        mantissa = (sample >> (exponent + 3)) & 0x0F
        ulaw_byte = ~(sign | (exponent << 4) | mantissa) & 0xFF
        out.append(ulaw_byte)

    return bytes(out)


def _ulaw_to_pcm16(ulaw_data: bytes) -> bytes:
    """Pure-Python fallback for G.711 μ-law to linear PCM 16-bit conversion."""
    if audioop is not None:
        try:
            return audioop.ulaw2lin(ulaw_data, 2)
        except Exception:
            pass

    out_samples = []
    for b in ulaw_data:
        inv = ~b & 0xFF
        sign = -1 if (inv & 0x80) else 1
        exponent = (inv >> 4) & 0x07
        mantissa = inv & 0x0F
        sample = ((mantissa << 3) + 0x84) << exponent
        val = max(-32768, min(32767, sign * (sample - 0x84)))
        out_samples.append(val)

    return struct.pack(f"<{len(out_samples)}h", *out_samples)


@dataclass(slots=True)
class QueuedPlaybackEntry:
    id: str
    text: str
    future: asyncio.Future[bool] | None = None
    generation_id: str | None = None
    status: str = "pending"  # "pending", "playing", "completed", "skipped", "failed"


class TTSEngine:
    """Telephony TTS engine supporting core TTS, ElevenLabs, and OpenAI overrides."""

    def __init__(self, default_config: VoiceCallTTSConfig | None = None) -> None:
        self.default_config = default_config or VoiceCallTTSConfig()
        self._pending_queues: dict[str, list[QueuedPlaybackEntry]] = {}

    def resolve_effective_tts_config(
        self,
        call_tts_override: VoiceCallTTSConfig | None,
        global_config: VoiceCallConfig,
    ) -> VoiceCallTTSConfig:
        """Deep merge call-specific TTS override with global config."""
        base = global_config.tts
        if not call_tts_override:
            return self._sanitize_tts_config(base)

        merged_options = dict(base.options)
        if call_tts_override.options:
            merged_options.update(call_tts_override.options)

        merged_providers = dict(base.providers)
        if call_tts_override.providers:
            for p_key, p_val in call_tts_override.providers.items():
                if isinstance(p_val, dict) and isinstance(merged_providers.get(p_key), dict):
                    deep_p = dict(merged_providers[p_key])
                    deep_p.update(p_val)
                    merged_providers[p_key] = deep_p
                else:
                    merged_providers[p_key] = p_val

        candidate = VoiceCallTTSConfig(
            provider=call_tts_override.provider or base.provider or "core",
            voice=call_tts_override.voice or base.voice,
            model=call_tts_override.model or base.model,
            options=merged_options,
            providers=merged_providers,
        )
        return self._sanitize_tts_config(candidate)

    def _sanitize_tts_config(self, config: VoiceCallTTSConfig) -> VoiceCallTTSConfig:
        """Filter out providers not implementing telephony-target output (e.g. Microsoft speech)."""
        prov = (config.provider or "core").lower().strip()
        if prov in ("microsoft", "edge"):
            logger.warning(
                "Microsoft speech is ignored for voice calls (requires telephony-target output). "
                "Falling back to core TTS provider chain."
            )
            return VoiceCallTTSConfig(
                provider="core",
                voice=config.voice,
                model=config.model,
                options=config.options,
                providers=config.providers,
            )
        return config

    def prepare_spoken_text(self, text: str, max_chars: int = 500) -> str:
        """Sanitize and trim text for telephony output."""
        cleaned = " ".join(text.strip().split())
        if len(cleaned) <= max_chars:
            return cleaned
        return cleaned[:max_chars].rstrip() + "..."

    def convert_pcm_to_mulaw_8k(self, pcm_data: bytes, sample_rate: int = 8000) -> bytes:
        """Convert linear PCM audio (16-bit mono) to 8kHz μ-law for telephony carriers."""
        return _pcm16_to_ulaw(pcm_data)

    def convert_mulaw_8k_to_pcm(self, mulaw_data: bytes, target_sample_rate: int = 8000) -> bytes:
        """Convert 8kHz μ-law audio from telephony carriers to 16-bit linear PCM."""
        return _ulaw_to_pcm16(mulaw_data)

    def clear_pending_queue(self, session_id: str, reason: str = "barge-in") -> int:
        """Clear pending TTS queue and settle in-flight futures as skipped so callers do not hang."""
        queue = self._pending_queues.pop(session_id, [])
        cleared_count = 0
        for entry in queue:
            entry.status = "skipped"
            if entry.future and not entry.future.done():
                entry.future.set_result(False)
            cleared_count += 1

        if cleared_count > 0:
            logger.info(
                "Cleared %d pending TTS playback entries for %s (reason=%s)",
                cleared_count,
                session_id,
                reason,
            )
        return cleared_count

    async def synthesize(
        self,
        text: str,
        config: VoiceCallTTSConfig,
        attempts: list[str] | None = None,
    ) -> dict[str, Any]:
        """Synthesize text into speech metadata/audio buffer with fallback logging."""
        prepared_text = self.prepare_spoken_text(text)
        effective_cfg = self._sanitize_tts_config(config)

        if attempts and len(attempts) > 1:
            logger.warning(
                "Telephony TTS fallback triggered: from=%s to=%s attempts=%s",
                attempts[0],
                effective_cfg.provider,
                attempts,
            )

        return {
            "text": prepared_text,
            "provider": effective_cfg.provider or "core",
            "voice": effective_cfg.voice or "default",
            "model": effective_cfg.model,
            "options": effective_cfg.options,
            "providers": effective_cfg.providers,
        }
