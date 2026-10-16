"""jarvis.talk.voice_confirmation — OpenClaw src/talk/client-voice-confirmation.ts parity.

Spoken confirmation binding for high-impact voice actions, refusal/affirmation
detection, and confirmation scope tracking across voice turns.
"""

from __future__ import annotations

import re
import time
import unicodedata
import uuid
from dataclasses import dataclass
from typing import Optional

CONFIRMATION_TTL_SEC = 120.0  # 2 minutes, matching OpenClaw CONFIRMATION_TTL_MS

REFUSAL_PATTERN = re.compile(
    r"\b(no|don'?t|do not|cancel|stop|never mind|haina|pardaina|nagara|nakhola|rok|hatai deu na)\b",
    re.I,
)

AFFIRMATION_PATTERN = re.compile(
    r"^\s*(yes|yes do it|do it|confirm|confirmed|go ahead|proceed|send it|make the change|"
    r"restart it|ho|gara|ho gara|garideu|banaideu|khola|kholideu|hatau|thik cha|okay do it|okay|sure|sure do it)\s*$",
    re.I,
)


def normalize_utterance(text: str) -> str:
    """Normalize utterance text for robust voice intent and confirmation matching."""
    if not text:
        return ""
    normalized = unicodedata.normalize("NFC", text.strip().lower())
    # Replace typographic quotes/apostrophes with ASCII single quote
    normalized = re.sub(r"[‘’ʼ`]", "'", normalized)
    # Devanagari vowel signs are Unicode marks, not regex word characters.
    # Preserve them or Nepali words are destroyed before intent matching.
    normalized = "".join(
        char
        if char.isalnum()
        or char.isspace()
        or char in "_'"
        or unicodedata.category(char).startswith("M")
        else " "
        for char in normalized
    )
    return " ".join(normalized.split())


def is_explicit_affirmation(text: str) -> bool:
    """Return True if the text represents an explicit affirmative confirmation."""
    normalized = normalize_utterance(text)
    if not normalized or is_explicit_refusal(normalized):
        return False
    return bool(AFFIRMATION_PATTERN.match(normalized))


def is_explicit_refusal(text: str) -> bool:
    """Return True if the text represents an explicit refusal or cancellation."""
    normalized = normalize_utterance(text)
    if not normalized:
        return False
    return bool(REFUSAL_PATTERN.search(normalized))


def requires_high_impact_voice_confirmation(tool_name: str, params: dict) -> bool:
    """Determine whether a tool action requires spoken voice confirmation.

    Mirrors OpenClaw's requiresHighImpactVoiceConfirmation:
    Destructive actions (remove_path, process kill without explicit request,
    dangerous shell execution) require explicit spoken confirmation.
    """
    normalized_tool = (tool_name or "").strip().lower()

    if normalized_tool == "remove_path":
        return True

    if normalized_tool == "exec":
        cmd = str(params.get("command", "")).lower()
        # High risk commands require confirmation
        dangerous = ["rm ", "del ", "format ", "drop ", "shutdown", "taskkill", "stop-process"]
        return any(d in cmd for d in dangerous)

    if normalized_tool == "process":
        action = str(params.get("action", "")).lower()
        # System-critical process terminations require confirmation
        if action == "kill":
            target = str(params.get("session_id", "")).lower()
            critical_processes = ["explorer", "system", "svchost", "csrss", "winlogon", "jarvis"]
            return any(c in target for c in critical_processes)

    return False


@dataclass(slots=True)
class PendingVoiceConfirmation:
    confirmation_id: str
    tool_name: str
    params: dict
    created_at: float
    expires_at: float


class VoiceConfirmationScope:
    """Manages pending voice confirmations and approval grants for a session."""

    def __init__(self, ttl_sec: float = CONFIRMATION_TTL_SEC) -> None:
        self.ttl_sec = ttl_sec
        self.pending: Optional[PendingVoiceConfirmation] = None
        self._approved_fingerprints: set[str] = set()

    def create_pending_confirmation(self, tool_name: str, params: dict) -> str:
        conf_id = str(uuid.uuid4())
        now = time.time()
        self.pending = PendingVoiceConfirmation(
            confirmation_id=conf_id,
            tool_name=tool_name,
            params=dict(params),
            created_at=now,
            expires_at=now + self.ttl_sec,
        )
        return conf_id

    def check_and_authorize(self, text: str) -> Optional[PendingVoiceConfirmation]:
        """Check if incoming utterance confirms or refuses pending action."""
        if not self.pending:
            return None

        now = time.time()
        if now > self.pending.expires_at:
            self.pending = None
            return None

        if is_explicit_refusal(text):
            self.pending = None
            return None

        if is_explicit_affirmation(text):
            confirmed = self.pending
            self.pending = None
            return confirmed

        return None

    def clear(self) -> None:
        self.pending = None
        self._approved_fingerprints.clear()
