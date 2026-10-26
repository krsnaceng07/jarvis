"""packages/voice_pipeline/tests/test_nepali_romanizer.py — Tests for Nepali romanizer."""

from __future__ import annotations

from jarvis_voice_pipeline.nepali_romanizer import (
    clean_phonetic_speech_artifacts,
    is_phantom_noise,
    romanize_nepali_text,
)


def test_romanize_tech_loanwords():
    assert romanize_nepali_text("ब्राइटनेस फुल गर त") == "Brightness full gara ta"
    assert "Volume" in romanize_nepali_text("भोल्युम ६०% बनाउ")
    assert "WhatsApp" in romanize_nepali_text("ह्वाट्सएप खोल")
    assert "Telegram" in romanize_nepali_text("टेलिग्राम चेक गर")
    assert "Settings" in romanize_nepali_text("सेटिङ्स खोल")


def test_romanize_devanagari_digits():
    assert romanize_nepali_text("६०%") == "60%"
    assert romanize_nepali_text("१००%") == "100%"
    assert romanize_nepali_text("५० प्रतिशत") == "50 %"


def test_phonetic_speech_artifact_cleaning():
    assert clean_phonetic_speech_artifacts("etanes phul karataa") == "Brightness full karataa"
    assert clean_phonetic_speech_artifacts("detanes phul") == "Brightness full"
    assert clean_phonetic_speech_artifacts("ts ap") == "WhatsApp"
    assert clean_phonetic_speech_artifacts("bholam timeele") == "Volume timeele"
    assert clean_phonetic_speech_artifacts("kunaiko hiro aayo") == "kunaiko error aayo"
    assert clean_phonetic_speech_artifacts("ke hiro chha") == "ke error chha"
    assert clean_phonetic_speech_artifacts("khet list karaa") == "delete karaa"
    assert clean_phonetic_speech_artifacts("tending nyooja़") == "trending news"
    assert clean_phonetic_speech_artifacts("stonik khola") == "Stonic AI khola"


def test_phantom_noise_detection():
    # Multi-lingual STT hallucinations on noise/silence
    assert is_phantom_noise("හෙरी කීයට ගන්නවා.") is True  # Sinhala
    assert is_phantom_noise("কি হতে পারে ना.") is True    # Bengali
    assert is_phantom_noise("稍微嗎?") is True           # Chinese
    assert is_phantom_noise("\u0ab5\u0abe\u0aa8\u0abe") is True         # Gujarati (વાના)
    assert is_phantom_noise(".") is True                  # Bare dot
    assert is_phantom_noise("...") is True                # Bare ellipsis
    assert is_phantom_noise("   ?  ") is True             # Bare question mark
    assert is_phantom_noise("") is True                   # Empty
    assert is_phantom_noise("<noise>") is True            # STT noise token
    assert is_phantom_noise("<noise> ") is True           # STT noise token with space
    assert is_phantom_noise("<silence>") is True          # STT silence token
    assert is_phantom_noise("[noise]") is True            # STT bracket noise

    # Genuine Nepali and English speech must NOT be marked as phantom noise
    assert is_phantom_noise("नमस्ते JARVIS") is False
    assert is_phantom_noise("smart krishna haina krishna maatr bhaneko thiyo") is False
    assert is_phantom_noise("Open Stonic AI please") is False
    assert is_phantom_noise("भोल्युम ६०% बनाउ") is False


def test_normalize_indic_to_devanagari_and_romanization():
    from jarvis_voice_pipeline.nepali_romanizer import normalize_indic_to_devanagari

    # Bengali decoded words are mapped to Devanagari and romanized smoothly
    bengali_text = "আবার ইউজার বেশ"
    dev = normalize_indic_to_devanagari(bengali_text)
    assert dev == "आबार इउजार बेश"
    rom = romanize_nepali_text(bengali_text)
    assert "aabaar" in rom

