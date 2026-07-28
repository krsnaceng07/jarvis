"""User-turn media marker — model-facing placeholder for blank media turns.

Mirrors OpenClaw's ``extensions/sessions/user-turn-media.ts``:
a single exported constant. The Python port keeps the same
name (``MEDIA_ONLY_USER_TEXT``) so the LLM-boundary code
in extensions can import it by the same identifier.
"""
from __future__ import annotations

# Model-facing marker for user turns that carry media but no
# caption. Never persist it as transcript content — UIs render
# content verbatim; the LLM boundary
# (``normalize_messages_for_llm_boundary``) injects it for
# blank media turns.
MEDIA_ONLY_USER_TEXT = "[User sent media without caption]"


__all__ = ["MEDIA_ONLY_USER_TEXT"]
