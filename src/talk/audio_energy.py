"""jarvis.talk.audio_energy — OpenClaw src/talk/audio-energy.ts parity.

Reads RMS and peak audio statistics from signed 16-bit PCM streams and provides
threshold-gated Voice Activity Detection (VAD) to prevent background noise,
room tone, and breathing from streaming into realtime models.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass
from typing import Callable, Optional

import numpy as np


@dataclass(frozen=True, slots=True)
class AudioEnergyStats:
    """RMS and absolute peak from signed 16-bit PCM audio samples."""

    rms: float
    peak: int


def read_pcm16_audio_stats(audio: bytes) -> AudioEnergyStats:
    """Calculate RMS and absolute peak from little-endian signed PCM16 samples."""
    if not audio:
        return AudioEnergyStats(rms=0.0, peak=0)
    samples = np.frombuffer(audio, dtype=np.int16)
    if len(samples) == 0:
        return AudioEnergyStats(rms=0.0, peak=0)
    peak = int(np.max(np.abs(samples)))
    rms = float(np.sqrt(np.mean(samples.astype(np.float64) ** 2)))
    return AudioEnergyStats(rms=rms, peak=peak)


def create_speech_threshold_gate(
    rms_threshold: Optional[float] = None,
    peak_threshold: Optional[int] = None,
    speech_frames: int = 1,
    silence_frames: int = 0,
    cooldown_ms: int = 0,
) -> SpeechThresholdGate:
    """Build an OR-threshold gate with optional sustained onset, silence hold, and cooldown."""
    return SpeechThresholdGate(
        rms_threshold=rms_threshold,
        peak_threshold=peak_threshold,
        speech_frames=speech_frames,
        silence_frames=silence_frames,
        cooldown_ms=cooldown_ms,
    )


class SpeechThresholdGate:
    """Stateful threshold gate matching OpenClaw's createSpeechThresholdGate."""

    def __init__(
        self,
        rms_threshold: Optional[float] = None,
        peak_threshold: Optional[int] = None,
        speech_frames: int = 1,
        silence_frames: int = 0,
        cooldown_ms: int = 0,
    ) -> None:
        self.rms_threshold = rms_threshold
        self.peak_threshold = peak_threshold
        self.speech_frames = max(1, speech_frames)
        self.silence_frames = max(0, silence_frames)
        self.cooldown_ms = max(0, cooldown_ms)
        self.loud_frames = 0
        self.quiet_frames = 0
        self.speaking = False
        self.last_trigger_at = -math.inf

    def accept(
        self,
        stats: AudioEnergyStats,
        now_ms: Optional[float] = None,
        on_trigger: Optional[Callable[[], bool]] = None,
    ) -> bool:
        loud = (self.rms_threshold is not None and stats.rms >= self.rms_threshold) or (
            self.peak_threshold is not None and stats.peak >= self.peak_threshold
        )
        if not loud:
            self.loud_frames = 0
            if self.speaking:
                self.quiet_frames += 1
                if self.quiet_frames >= self.silence_frames:
                    self.speaking = False
            return False

        self.quiet_frames = 0
        self.loud_frames += 1
        if self.speaking or self.loud_frames < self.speech_frames:
            return False

        import time

        current_ms = now_ms if now_ms is not None else (time.time() * 1000.0)
        if current_ms - self.last_trigger_at < self.cooldown_ms:
            return False
        if on_trigger is not None and not on_trigger():
            return False

        self.last_trigger_at = current_ms
        self.speaking = self.silence_frames > 0
        if not self.speaking:
            self.loud_frames = 0
        return True


class SpeechStreamVADGate:
    """Continuous stream VAD gate with speech onset and silence hangover.

    Allows streaming audio chunks through while speech is active and holds the gate
    open for a configurable number of quiet frames (hangover) so pauses between words
    are not clipped, while effectively filtering out room silence and static hum.
    Supports dynamic ambient noise-floor tracking for sensitive far-field capture.
    """

    def __init__(
        self,
        rms_threshold: float = 14.0,
        peak_threshold: int = 80,
        hangover_frames: int = 22,
        onset_frames: int = 1,
        adaptive: bool = True,
        min_rms_threshold: float = 8.0,
        ambient_alpha: float = 0.05,
    ) -> None:
        self.rms_threshold = rms_threshold
        self.peak_threshold = peak_threshold
        self.hangover_frames = max(1, hangover_frames)
        self.onset_frames = max(1, onset_frames)
        self.adaptive = adaptive
        self.min_rms_threshold = min_rms_threshold
        self.ambient_alpha = ambient_alpha
        self._consecutive_loud = 0
        self._consecutive_quiet = 0
        self._is_active = False
        self._ambient_rms: float = min_rms_threshold
        self._ambient_peak: float = float(peak_threshold // 4)
        self._recent_rms: deque[float] = deque(maxlen=25)
        self._recent_peak: deque[int] = deque(maxlen=25)

    @property
    def is_speech_active(self) -> bool:
        return self._is_active

    @property
    def ambient_rms(self) -> float:
        return self._ambient_rms

    @property
    def ambient_peak(self) -> float:
        return self._ambient_peak

    def get_effective_thresholds(self) -> tuple[float, int]:
        """Compute the active (rms, peak) thresholds taking ambient noise into account."""
        if not self.adaptive:
            return self.rms_threshold, self.peak_threshold

        # In quiet environments, adapt down toward min_rms_threshold to hear distant speech/whispers.
        # In noisier environments (fan/AC hum), adapt upward above the ambient noise floor.
        if self._ambient_rms < self.rms_threshold:
            effective_rms = max(
                self.min_rms_threshold,
                min(self.rms_threshold, self._ambient_rms * 1.5 + 3.0),
            )
        else:
            effective_rms = max(self.rms_threshold, self._ambient_rms * 1.35 + 3.0)

        if self._ambient_peak < self.peak_threshold:
            effective_peak = max(
                int(self.peak_threshold * 0.65),
                min(self.peak_threshold, int(self._ambient_peak * 2.0 + 20)),
            )
        else:
            effective_peak = max(self.peak_threshold, int(self._ambient_peak * 1.35 + 20))

        return effective_rms, effective_peak

    def filter_chunk(self, chunk: bytes) -> bool:
        """Returns True if chunk contains voice activity or is within the hangover window."""
        stats = read_pcm16_audio_stats(chunk)
        eff_rms, eff_peak = self.get_effective_thresholds()

        is_loud = (stats.rms >= eff_rms or stats.peak >= eff_peak)

        if self._is_active:
            # While active, continue active state if chunk meets threshold
            if is_loud:
                self._consecutive_quiet = 0
                return True
            else:
                self._consecutive_quiet += 1
                if self._consecutive_quiet <= self.hangover_frames:
                    return True
                else:
                    self._is_active = False
                    self._consecutive_loud = 0
                    return False
        else:
            # Voice onset detection: requires peak reaching effective peak or loud RMS with reasonable crest
            is_onset = is_loud and (
                stats.peak >= eff_peak or (stats.rms >= eff_rms and stats.peak >= int(eff_peak * 0.6))
            )
            if is_onset:
                self._consecutive_quiet = 0
                self._consecutive_loud += 1
                if self._consecutive_loud >= self.onset_frames:
                    self._is_active = True
                return True
            else:
                self._consecutive_loud = 0
                # Ambient noise floor tracking during confirmed quiet periods
                if self.adaptive and stats.rms > 0:
                    self._recent_rms.append(stats.rms)
                    self._recent_peak.append(stats.peak)
                    min_rms = min(self._recent_rms)
                    min_peak = min(self._recent_peak)
                    if len(self._recent_rms) <= 5:
                        self._ambient_rms = min_rms
                        self._ambient_peak = float(min_peak)
                    else:
                        self._ambient_rms = (
                            (1.0 - self.ambient_alpha) * self._ambient_rms
                            + self.ambient_alpha * min_rms
                        )
                        self._ambient_peak = (
                            (1.0 - self.ambient_alpha) * self._ambient_peak
                            + self.ambient_alpha * min_peak
                        )
                return False

    def reset(self) -> None:
        self._consecutive_loud = 0
        self._consecutive_quiet = 0
        self._is_active = False
