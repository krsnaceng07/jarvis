"""Tests for OpenClaw-parity Voice Activity Detection, Speech Grounding, and Voice Confirmation."""

from __future__ import annotations

import numpy as np
import pytest

from src.talk.audio_energy import (
    AudioEnergyStats,
    SpeechStreamVADGate,
    create_speech_threshold_gate,
    read_pcm16_audio_stats,
)
from src.talk.speech_guard import SpeechGroundingGuard
from src.talk.voice_confirmation import (
    is_explicit_affirmation,
    is_explicit_refusal,
    normalize_utterance,
    requires_high_impact_voice_confirmation,
)


def _make_pcm16_tone(
    frequency: float = 440.0,
    duration_sec: float = 0.05,
    sample_rate: int = 16000,
    amplitude: int = 5000,
) -> bytes:
    t = np.linspace(0, duration_sec, int(sample_rate * duration_sec), endpoint=False)
    samples = (amplitude * np.sin(2 * np.pi * frequency * t)).astype(np.int16)
    return samples.tobytes()


def _make_pcm16_silence(duration_sec: float = 0.05, sample_rate: int = 16000) -> bytes:
    samples = np.zeros(int(sample_rate * duration_sec), dtype=np.int16)
    return samples.tobytes()


class TestAudioEnergyAndVADParity:
    def test_read_pcm16_audio_stats_silence(self):
        silence = _make_pcm16_silence()
        stats = read_pcm16_audio_stats(silence)
        assert stats.rms == 0.0
        assert stats.peak == 0

    def test_read_pcm16_audio_stats_tone(self):
        tone = _make_pcm16_tone(amplitude=4000)
        stats = read_pcm16_audio_stats(tone)
        assert stats.peak > 3900
        # RMS of a sine wave is amplitude / sqrt(2) ~ 2828
        assert 2700 < stats.rms < 2950

    def test_speech_threshold_gate_rearms_after_silence(self):
        gate = create_speech_threshold_gate(
            rms_threshold=500.0,
            speech_frames=2,
            silence_frames=2,
        )
        loud = AudioEnergyStats(rms=1000.0, peak=2000)
        quiet = AudioEnergyStats(rms=100.0, peak=200)

        assert gate.accept(loud) is False  # frame 1 (onset check)
        assert gate.accept(loud) is True  # frame 2 (sustained onset -> fires trigger)
        assert gate.accept(loud) is False  # already speaking
        assert gate.accept(quiet) is False  # quiet 1
        assert gate.accept(quiet) is False  # quiet 2 -> re-armed
        assert gate.accept(loud) is False  # onset 1
        assert gate.accept(loud) is True  # onset 2 -> fires trigger

    def test_speech_stream_vad_gate_hangover(self):
        vad = SpeechStreamVADGate(
            rms_threshold=500.0,
            peak_threshold=1000,
            hangover_frames=3,
            onset_frames=1,
        )
        loud_chunk = _make_pcm16_tone(amplitude=3000)
        silence_chunk = _make_pcm16_silence()

        # Loud chunk passes and marks speech active
        assert vad.filter_chunk(loud_chunk) is True
        assert vad.is_speech_active is True

        # Silence chunks pass during hangover (3 frames)
        assert vad.filter_chunk(silence_chunk) is True
        assert vad.filter_chunk(silence_chunk) is True
        assert vad.filter_chunk(silence_chunk) is True
        assert vad.is_speech_active is True

        # Frame 4 of silence exceeds hangover -> dropped and speech becomes inactive
        assert vad.filter_chunk(silence_chunk) is False
        assert vad.is_speech_active is False


class TestUtteranceAndConfirmationParity:
    def test_normalize_utterance(self):
        raw = "  Hello, world! It’s working…  "
        assert normalize_utterance(raw) == "hello world it's working"

    def test_affirmations_and_refusals_multilingual(self):
        # English affirmations
        assert is_explicit_affirmation("yes") is True
        assert is_explicit_affirmation("yes do it") is True
        assert is_explicit_affirmation("confirmed") is True
        assert is_explicit_affirmation("go ahead") is True

        # Nepali affirmations
        assert is_explicit_affirmation("ho") is True
        assert is_explicit_affirmation("gara") is True
        assert is_explicit_affirmation("garideu") is True
        assert is_explicit_affirmation("khola") is True
        assert is_explicit_affirmation("thik cha") is True

        # English refusals
        assert is_explicit_refusal("no") is True
        assert is_explicit_refusal("don't") is True
        assert is_explicit_refusal("cancel") is True
        assert is_explicit_refusal("stop") is True

        # Nepali refusals
        assert is_explicit_refusal("haina") is True
        assert is_explicit_refusal("pardaina") is True
        assert is_explicit_refusal("nagara") is True
        assert is_explicit_refusal("rok") is True

    def test_requires_high_impact_voice_confirmation(self):
        assert requires_high_impact_voice_confirmation("remove_path", {"path": "test.txt"}) is True
        assert requires_high_impact_voice_confirmation("exec", {"command": "rm -rf foo"}) is True
        assert requires_high_impact_voice_confirmation("exec", {"command": "dir"}) is False
        assert requires_high_impact_voice_confirmation("open_path", {"target": "notepad"}) is False
        assert requires_high_impact_voice_confirmation("ls", {"path": "C:/"}) is False


class TestSpeechGroundingGuardParity:
    @pytest.fixture
    def guard(self):
        return SpeechGroundingGuard()

    def test_empty_or_filler_blocks_tool_with_clarification(self, guard):
        # Empty speech
        res1 = guard.validate_voice_tool_call("open_path", {"target": "notepad"}, "")
        assert res1.is_allowed is False
        assert "UNGROUNDED VOICE INTERCEPTION" in res1.clarification_message

        # Pure filler sound
        res2 = guard.validate_voice_tool_call(
            "process", {"action": "kill", "session_id": "notepad"}, "uh um hmm"
        )
        assert res2.is_allowed is False
        assert "filler sound" in res2.clarification_message

    def test_ambiguous_commands_require_clarification(self, guard):
        # Ambiguous open ("khol" without target)
        res1 = guard.validate_voice_tool_call("open_path", {"target": "notepad"}, "kholideu")
        assert res1.is_allowed is False
        assert "What would you like me to open" in res1.clarification_message

        # Ambiguous close
        res2 = guard.validate_voice_tool_call("process", {"action": "kill"}, "banda gara")
        assert res2.is_allowed is False
        assert "Which application would you like me to close" in res2.clarification_message

        # Ambiguous delete
        res3 = guard.validate_voice_tool_call("remove_path", {"path": "important.txt"}, "delete")
        assert res3.is_allowed is False
        assert "Which file or folder would you like to delete" in res3.clarification_message

    def test_semantic_tool_alignment_repairs_mismatches(self, guard):
        # Case A: User said "open notepad", model hallucinated "browser"
        res_open = guard.validate_voice_tool_call(
            "browser", {"url": "https://notepad.com"}, "open notepad"
        )
        assert res_open.is_allowed is True
        assert res_open.repaired_tool_name == "open_path"
        assert res_open.repaired_args == {"target": "notepad"}

        # Case B: User said "open calculator", model hallucinated "process(kill)"
        res_calc = guard.validate_voice_tool_call(
            "process", {"action": "kill", "session_id": "calculator"}, "calculator khola"
        )
        assert res_calc.is_allowed is True
        assert res_calc.repaired_tool_name == "open_path"
        assert res_calc.repaired_args == {"target": "calculator"}

        # Case C: User said "search python on youtube", model hallucinated "open_path"
        res_search = guard.validate_voice_tool_call(
            "open_path", {"target": "youtube"}, "search python on youtube"
        )
        assert res_search.is_allowed is True
        assert res_search.repaired_tool_name == "browser"
        assert "youtube.com" in res_search.repaired_args["url"]

        # Case D: User said "notepad banda gara", model hallucinated "browser"
        res_close = guard.validate_voice_tool_call(
            "browser", {"url": "http://close"}, "notepad banda gara"
        )
        assert res_close.is_allowed is True
        assert res_close.repaired_tool_name == "process"
        assert res_close.repaired_args == {"action": "kill", "session_id": "notepad"}

    def test_spoken_confirmation_lifecycle_flow(self, guard):
        # Conversation must not turn a model-invented deletion into a pending action.
        res = guard.validate_voice_tool_call(
            "remove_path", {"path": "critical_doc.pdf"}, "maybe we should check"
        )
        assert res.is_allowed is False
        assert res.requires_confirmation is False
        assert guard.confirmation_scope.pending is None

        # Next turn user says "ho gara" (Yes, do it!)
        res_affirmed = guard.validate_voice_tool_call(
            "remove_path", {"path": "critical_doc.pdf"}, "ho gara"
        )
        assert res_affirmed.is_allowed is False

    def test_spoken_cancellation_flow(self, guard):
        # High impact action triggers confirmation
        res = guard.validate_voice_tool_call(
            "remove_path", {"path": "file.txt"}, "can you delete it"
        )
        # No resolved spoken target: the model cannot invent file.txt.
        assert res.is_allowed is False

        # Now test vague utterance triggering confirmation
        res_vague = guard.validate_voice_tool_call(
            "remove_path", {"path": "file.txt"}, "i was thinking"
        )
        assert res_vague.is_allowed is False
        assert res_vague.requires_confirmation is False

        # User declines: "haina pardaina"
        res_declined = guard.validate_voice_tool_call(
            "remove_path", {"path": "file.txt"}, "haina pardaina"
        )
        assert res_declined.is_allowed is False
        assert guard.confirmation_scope.pending is None

    def test_youtube_open_karo_intent_and_browser_preservation(self, guard):
        from src.agents.decision.intent import IntentClassifier, IntentCategory

        # 1. "youtube open karo" must classify as ACTIONABLE_BROWSER targeting youtube
        intent = IntentClassifier.classify("youtube open karo")
        assert intent.category == IntentCategory.ACTIONABLE_BROWSER
        assert intent.primary_tool == "browser"
        assert intent.target_entity == "youtube"
        assert intent.parameters.get("action") == "open"
        assert "youtube.com" in intent.parameters.get("url", "")

        # 2. Guard must NEVER repair browser to open_path(target="karo")
        res_yt = guard.validate_voice_tool_call(
            "browser", {"action": "open", "url": "https://www.youtube.com"}, "youtube open karo"
        )
        assert res_yt.is_allowed is True
        assert res_yt.repaired_tool_name is None  # Preserves browser, does not hijack to open_path

    def test_auxiliary_verb_karo_not_extracted_as_entity(self, guard):
        from src.agents.decision.intent import IntentClassifier

        # 1. "open karo" without an app name must NOT extract target="karo"
        intent = IntentClassifier.classify("open karo")
        assert intent.target_entity != "karo"
        assert intent.primary_tool != "open_path"

        # 2. "khol karo" must NOT extract target="karo"
        intent_khol = IntentClassifier.classify("khol karo")
        assert intent_khol.target_entity != "karo"

    def test_vad_low_amplitude_natural_speech_passes(self):
        # Conversational speech with RMS around 35 passes without being chopped
        vad = SpeechStreamVADGate()
        speech_chunk = _make_pcm16_tone(amplitude=200)  # gentle tone
        assert vad.filter_chunk(speech_chunk) is True
        assert vad.is_speech_active is True
