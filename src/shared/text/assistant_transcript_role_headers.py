"""jarvis.shared.text.assistant_transcript_role_headers — detect transcript-role headers.

OpenClaw parity: mirrors
``openclaw-main/src/shared/text/assistant-transcript-role-headers.ts``.

The Python port exposes a focused minimal surface: detection of transcript
role headers in plain text. Full Markdown IR parsing is delegated to the
caller via the ``annotations`` param of :func:`detect_assistant_transcript
_role_header_text`.
"""
from __future__ import annotations

from typing import Literal, Optional, TypedDict


AssistantRole = Literal["assistant", "developer", "system", "user"]


class AssistantTranscriptRoleHeaderDetection(TypedDict, total=False):
    kind: str  # "angle_role_header" | "role_timestamp_bracket" | "timestamp_role_colon"
    role: AssistantRole


# Recognized transcript role header patterns. The first match wins.
_ANGLE_HEADER_RE = __import__("re").compile(
    r"^\s*<\s*(?P<role>assistant|developer|system|user)\s*>",
    __import__("re").IGNORECASE,
)
_BRACKET_HEADER_RE = __import__("re").compile(
    r"^\s*\[\s*(?P<role>assistant|developer|system|user)\s+[^]]+\]",
    __import__("re").IGNORECASE,
)
_COLON_HEADER_RE = __import__("re").compile(
    r"^\s*(?P<role>assistant|developer|system|user)\s*:",
    __import__("re").IGNORECASE,
)


def detect_assistant_transcript_role_header_text(
    text: str,
    annotations: Optional[list] = None,
) -> Optional[AssistantTranscriptRoleHeaderDetection]:
    """Detect transcript-role header prefixes in ``text``.

    Mirrors :func:`detectAssistantTranscriptRoleHeaderText`
    (``shared/text/assistant-transcript-role-headers.ts``).
    """
    # If the caller passed Markdown-IR annotations, use the parser-driven
    # detection path.
    if annotations:
        for ann in annotations:
            if not isinstance(ann, dict):
                continue
            if ann.get("type") == "assistant_transcript_role":
                kind = ann.get("kind") or "angle_role_header"
                role = ann.get("role") or "assistant"
                return {"kind": kind, "role": role}
    # Fall back to plain-text pattern detection.
    if not isinstance(text, str):
        return None
    m = _ANGLE_HEADER_RE.match(text)
    if m:
        return {"kind": "angle_role_header", "role": m.group("role").lower()}
    m = _BRACKET_HEADER_RE.match(text)
    if m:
        return {"kind": "role_timestamp_bracket", "role": m.group("role").lower()}
    m = _COLON_HEADER_RE.match(text)
    if m:
        return {"kind": "timestamp_role_colon", "role": m.group("role").lower()}
    return None


__all__ = [
    "AssistantTranscriptRoleHeaderDetection",
    "AssistantRole",
    "detect_assistant_transcript_role_header_text",
]
