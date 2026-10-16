"""tests.test_audio_energy_vad — Verification of SpeechStreamVADGate far-field sensitivity and noise adaptation."""

from __future__ import annotations

import numpy as np
import pytest

from src.talk.audio_energy import (
    SpeechStreamVADGate,
    read_pcm16_audio_stats,
)


def _make_pcm_chunk(amplitude: int, count: int = 1024) -> bytes:
    """Generate a dummy 16-bit PCM chunk with a uniform or sinusoidal amplitude."""
    if amplitude == 0:
        return np.zeros(count, dtype=np.int16).tobytes()
    # Simple sine wave with specified peak amplitude
    t = np.linspace(0, 2 * np.pi, count, endpoint=False)
    samples = (np.sin(t * 10) * amplitude).astype(np.int16)
    return samples.tobytes()


def test_pcm16_stats_calculation():
    """Verify RMS and peak calculation for PCM16 audio."""
    # Absolute silence
    silence = _make_pcm_chunk(0)
    stats = read_pcm16_audio_stats(silence)
    assert stats.rms == 0.0
    assert stats.peak == 0

    # Low amplitude distant speech signal (peak 100)
    quiet_chunk = _make_pcm_chunk(100)
    stats_quiet = read_pcm16_audio_stats(quiet_chunk)
    assert stats_quiet.peak == pytest.approx(100, abs=5)
    assert 60.0 <= stats_quiet.rms <= 80.0


def test_vad_far_field_speech_detected():
    """Distant speech (e.g. RMS ~16, peak ~90) should trigger the new far-field VAD defaults."""
    vad = SpeechStreamVADGate(
        rms_threshold=14.0,
        peak_threshold=80,
        hangover_frames=22,
        adaptive=True,
    )

    # Distant speech audio chunk
    distant_chunk = _make_pcm_chunk(90)
    stats = read_pcm16_audio_stats(distant_chunk)
    assert stats.rms >= 14.0 or stats.peak >= 80

    result = vad.filter_chunk(distant_chunk)
    assert result is True
    assert vad.is_speech_active is True


def test_vad_silence_filtering():
    """Background silence or very low noise should be filtered out."""
    vad = SpeechStreamVADGate(
        rms_threshold=14.0,
        peak_threshold=80,
        hangover_frames=22,
        adaptive=False,
    )

    # Ambient room tone (peak 15)
    noise_chunk = _make_pcm_chunk(15)
    result = vad.filter_chunk(noise_chunk)
    assert result is False
    assert vad.is_speech_active is False


def test_vad_hangover_prevents_premature_cutoff():
    """Hangover frames should keep the gate open across short conversational pauses."""
    vad = SpeechStreamVADGate(
        rms_threshold=14.0,
        peak_threshold=80,
        hangover_frames=5,
        adaptive=False,
    )

    # 1. Trigger speech
    speech_chunk = _make_pcm_chunk(120)
    assert vad.filter_chunk(speech_chunk) is True
    assert vad.is_speech_active is True

    # 2. Quiet pause (between words) for 5 frames - should stay open
    pause_chunk = _make_pcm_chunk(5)
    for i in range(5):
        assert vad.filter_chunk(pause_chunk) is True, f"Frame {i+1} in hangover should pass"
        assert vad.is_speech_active is True

    # 3. 6th quiet frame exceeds hangover - should close gate
    assert vad.filter_chunk(pause_chunk) is False
    assert vad.is_speech_active is False


def test_adaptive_noise_floor_quiet_room():
    """In a quiet room, adaptive tracking lowers effective RMS threshold towards min_rms_threshold."""
    vad = SpeechStreamVADGate(
        rms_threshold=14.0,
        peak_threshold=80,
        min_rms_threshold=8.0,
        adaptive=True,
        ambient_alpha=0.5,  # fast adaptation for test
    )

    # Feed multiple quiet chunks (ambient noise ~ 3 RMS)
    very_quiet_chunk = _make_pcm_chunk(5)
    for _ in range(10):
        vad.filter_chunk(very_quiet_chunk)

    eff_rms, eff_peak = vad.get_effective_thresholds()
    # In a quiet room, threshold adapts down, allowing sensitive far-field capture
    assert eff_rms < 14.0
    assert eff_rms >= 8.0


def test_adaptive_noise_floor_noisy_room():
    """In a room with steady noise (fan/AC), effective threshold adapts upward to avoid false triggering."""
    vad = SpeechStreamVADGate(
        rms_threshold=14.0,
        peak_threshold=80,
        min_rms_threshold=8.0,
        adaptive=True,
        ambient_alpha=0.5,
    )

    # Steady fan hum (peak 30, RMS ~ 20)
    fan_chunk = _make_pcm_chunk(30)
    for _ in range(10):
        vad.filter_chunk(fan_chunk)

    eff_rms, _ = vad.get_effective_thresholds()
    # The effective threshold should adapt upward to sit safely above the fan noise
    assert eff_rms > 14.0

    # User speaks loudly over the fan
    loud_speech = _make_pcm_chunk(200)
    assert vad.filter_chunk(loud_speech) is True
    assert vad.is_speech_active is True


def test_vad_reset():
    """Reset should clear consecutive counters and speech active state."""
    vad = SpeechStreamVADGate(rms_threshold=14.0, peak_threshold=80)
    vad.filter_chunk(_make_pcm_chunk(150))
    assert vad.is_speech_active is True

    vad.reset()
    assert vad.is_speech_active is False


def test_mic_digital_gain_clamping():
    """Verify that software digital gain amplifies weak audio while clamping safely."""
    # Distant quiet samples
    mono = np.array([-50, 0, 80, 120, -100], dtype=np.int32)
    mic_gain = 2.0
    boosted = np.clip(mono.astype(np.float32) * mic_gain, -32768, 32767).astype(np.int32)
    np.testing.assert_array_equal(boosted, np.array([-100, 0, 160, 240, -200]))

    # Extreme loud samples clamping safely to int16 boundaries
    extreme = np.array([-30000, 30000], dtype=np.int32)
    boosted_extreme = np.clip(extreme.astype(np.float32) * mic_gain, -32768, 32767).astype(np.int32)
    np.testing.assert_array_equal(boosted_extreme, np.array([-32768, 32767]))

