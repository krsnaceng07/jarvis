"""jarvis.talk — OpenClaw src/talk/ parity.

Voice Activity Detection (VAD), audio energy calculation, spoken confirmation,
and speech-to-intent grounding.
"""

from src.talk.audio_energy import (
    AudioEnergyStats,
    SpeechStreamVADGate,
    SpeechThresholdGate,
    create_speech_threshold_gate,
    read_pcm16_audio_stats,
)
from src.talk.speech_guard import SpeechGroundingGuard, SpeechGroundingResult
from src.talk.voice_confirmation import (
    VoiceConfirmationScope,
    is_explicit_affirmation,
    is_explicit_refusal,
    normalize_utterance,
    requires_high_impact_voice_confirmation,
)

from src.talk.speech_synthesizer import (
    clean_text_for_speech,
    synthesize_speech_wav,
    synthesize_speech_wav_async,
)

__all__ = [
    "AudioEnergyStats",
    "SpeechStreamVADGate",
    "SpeechThresholdGate",
    "create_speech_threshold_gate",
    "read_pcm16_audio_stats",
    "SpeechGroundingGuard",
    "SpeechGroundingResult",
    "VoiceConfirmationScope",
    "is_explicit_affirmation",
    "is_explicit_refusal",
    "normalize_utterance",
    "requires_high_impact_voice_confirmation",
    "clean_text_for_speech",
    "synthesize_speech_wav",
    "synthesize_speech_wav_async",
]

