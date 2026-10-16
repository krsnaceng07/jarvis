"""Speech Synthesizer — OpenClaw talk parity.

Synthesizes textual replies into WAV audio bytes for external channel delivery
(Telegram voice notes, WhatsApp voice notes, etc.) without playing any audio
on local desktop speakers.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import tempfile

_log = logging.getLogger("jarvis.talk.synthesizer")


def clean_text_for_speech(text: str) -> str:
    """Strip markdown formatting, URLs, code blocks, and symbols for clean spoken audio."""
    if not text:
        return ""
    # Remove code blocks
    cleaned = re.sub(r"```[\s\S]*?```", " [Code snippet omitted] ", text)
    # Remove inline code
    cleaned = re.sub(r"`([^`]+)`", r"\1", cleaned)
    # Remove markdown links [text](url) -> text
    cleaned = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", cleaned)
    # Remove raw URLs
    cleaned = re.sub(r"https?://\S+", "", cleaned)
    # Remove markdown headers, bullets, bold, italics
    cleaned = re.sub(r"^#{1,6}\s+", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"\*{1,3}", "", cleaned)
    cleaned = re.sub(r"~{1,2}", "", cleaned)
    cleaned = re.sub(r"(?<!\w)_(?=\w)|(?<=\w)_(?!\w)", "", cleaned)
    cleaned = re.sub(r"^[ \t]*[-*+]\s+", "", cleaned, flags=re.MULTILINE)
    # Normalize multiple whitespace and newlines
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    # If message is very verbose, truncate for responsive, concise spoken voice note
    if len(cleaned) > 800:
        cleaned = cleaned[:797] + "..."
    return cleaned


def synthesize_speech_wav(text: str) -> bytes | None:
    """Synthesize text into WAV audio bytes in-memory without desktop speaker playback.

    Uses Windows SAPI via pywin32 with SpFileStream.
    """
    clean_text = clean_text_for_speech(text)
    if not clean_text:
        return None

    try:
        import pythoncom
        import win32com.client

        pythoncom.CoInitialize()
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
                temp_path = tf.name

            # SSFMCreateForWrite = 3
            stream = win32com.client.Dispatch("SAPI.SpFileStream")
            stream.Open(temp_path, 3)

            voice = win32com.client.Dispatch("SAPI.SpVoice")
            voice.AudioOutputStream = stream
            voice.Speak(clean_text)
            stream.Close()

            with open(temp_path, "rb") as f:
                wav_bytes = f.read()

            return wav_bytes if wav_bytes else None
        finally:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except Exception:
                    pass
            pythoncom.CoUninitialize()
    except Exception as e:
        _log.warning("Speech synthesis failed: %s", e)
        return None


async def synthesize_speech_wav_async(text: str) -> bytes | None:
    """Asynchronously synthesize text into WAV audio bytes."""
    return await asyncio.to_thread(synthesize_speech_wav, text)


__all__ = [
    "clean_text_for_speech",
    "synthesize_speech_wav",
    "synthesize_speech_wav_async",
]
