"""packages/voice_pipeline/src/jarvis_voice_pipeline/outcome.py

Outcome formatting for tool outputs.
Provides structured, language-neutral machine facts rather than rigid English prose,
enabling Gemini to naturally reply in the user's spoken language.
"""

from __future__ import annotations

import re
from typing import Any

DONE = "done"
UNVERIFIED = "unverified"
FAILED = "failed"
ASK = "ask"
STARTED = "started"


def _render(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    text = str(value).replace('"', "'").replace("\n", " ").strip()
    return f'"{text}"' if (" " in text or not text) else text


def _line(status: str, action: str, facts: dict[str, Any]) -> str:
    parts = [f"status={status}", f"action={action}"]
    parts += [f"{k}={_render(v)}" for k, v in facts.items() if v is not None]
    return " ".join(parts)


def done(action: str, /, **facts: Any) -> str:
    """Action was executed and verified against real state."""
    return _line(DONE, action, facts)


def unverified(action: str, reason: str, /, **facts: Any) -> str:
    """Action was requested, but state could not be verified."""
    return _line(UNVERIFIED, action, {**facts, "reason": reason}) + (
        " -- NOT confirmed. Tell the user plainly that you asked and cannot "
        "confirm it worked, and say what they can check. Do NOT say it is done."
    )


def failed(action: str, reason: str, /, **facts: Any) -> str:
    """Action did not succeed."""
    return _line(FAILED, action, {**facts, "reason": reason}) + (
        " -- This did NOT happen. Tell the user so in their own language, with "
        "the reason. Do not claim any part of it succeeded."
    )


def started(action: str, /, **facts: Any) -> str:
    """Action is under way in the background."""
    return _line(STARTED, action, facts) + (
        " -- UNDER WAY, not finished. Say in one short sentence, in the user's "
        "own language, that it is being done. Do not say it is complete."
    )


def ask(action: str, question: str, /, **facts: Any) -> str:
    """Action was paused to ask clarification from user."""
    return _line(ASK, action, {**facts, "question": question}) + (
        " -- NOTHING was done yet. Put this question to the user in their own "
        "language and wait for their answer before calling again."
    )


def unwrap(text: str) -> str:
    """Strip outcome instruction markers from user display."""
    return re.sub(r"\s*--\s+.*$", "", text).strip()
