"""Session label parsing.

Mirrors OpenClaw's ``extensions/sessions/session-label.ts``:
``SESSION_LABEL_MAX_LENGTH`` + ``parse_session_label`` with
structured result envelope (``{ok: True, label}`` or
``{ok: False, error}``). The Python port uses
``dataclass`` for the result envelope.
"""

from __future__ import annotations

from dataclasses import dataclass

# User-editable session labels are short display strings
# saved in session metadata. Mirrors the TS
# ``SESSION_LABEL_MAX_LENGTH`` constant.
SESSION_LABEL_MAX_LENGTH = 512


@dataclass(frozen=True, slots=True)
class ParsedSessionLabel:
    """Result of ``parse_session_label``.

    Mirrors the TS ``ParsedSessionLabel = {ok: True, label} |
    {ok: False, error}`` discriminated union.
    """

    ok: bool
    label: str | None = None
    error: str | None = None


def parse_session_label(raw: object) -> ParsedSessionLabel:
    """Validate a user-supplied session label.

    Returns a ``ParsedSessionLabel`` with ``ok=True`` and the
    trimmed label, or ``ok=False`` and a structured error
    message. Mirrors the TS ``parseSessionLabel``.
    """
    if not isinstance(raw, str):
        return ParsedSessionLabel(ok=False, error="invalid label: must be a string")
    trimmed = raw.strip()
    if not trimmed:
        return ParsedSessionLabel(ok=False, error="invalid label: empty")
    if len(trimmed) > SESSION_LABEL_MAX_LENGTH:
        return ParsedSessionLabel(
            ok=False,
            error=f"invalid label: too long (max {SESSION_LABEL_MAX_LENGTH})",
        )
    return ParsedSessionLabel(ok=True, label=trimmed)


__all__ = [
    "ParsedSessionLabel",
    "SESSION_LABEL_MAX_LENGTH",
    "parse_session_label",
]
