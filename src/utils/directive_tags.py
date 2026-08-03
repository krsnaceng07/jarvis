"""jarvis.utils.directive_tags — parse inline directive tags from user text.

OpenClaw parity: mirrors ``openclaw-main/src/utils/directive-tags.ts``.

Public surface:

- :class:`InlineDirectiveParseResult`
- :class:`DisplayMessageWithContent`
- :func:`strip_inline_directive_tags_for_display`
- :func:`strip_inline_directive_tags_for_delivery`
- :func:`strip_inline_directive_tags_from_message_for_display`
- :func:`sanitize_reply_directive_id`
- :func:`parse_inline_directives`
- :data:`MAX_REPLY_DIRECTIVE_ID_LENGTH`
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional


MAX_REPLY_DIRECTIVE_ID_LENGTH = 256

_AUDIO_TAG_RE = re.compile(r"\[\[\s*audio_as_voice\s*\]\]", re.IGNORECASE)
_REPLY_TAG_RE = re.compile(
    r"\[\[\s*(?:reply_to_current|reply_to\s*:\s*([^\]\n]+))\s*\]\]", re.IGNORECASE
)
_INLINE_DIRECTIVE_TAG_WITH_PADDING_RE = re.compile(
    r"\s*(?:\[\[\s*audio_as_voice\s*\]\]|\[\[\s*(?:reply_to_current|reply_to\s*:\s*[^\]\n]+)\s*\]\])\s*",
    re.IGNORECASE,
)


class InlineDirectiveParseResult:
    """Result of parsing inline directive tags from user text."""

    def __init__(
        self,
        text: str = "",
        audio_as_voice: bool = False,
        reply_to_id: Optional[str] = None,
        reply_to_explicit_id: Optional[str] = None,
        reply_to_current: bool = False,
        has_audio_tag: bool = False,
        has_reply_tag: bool = False,
    ) -> None:
        self.text = text
        self.audio_as_voice = audio_as_voice
        self.reply_to_id = reply_to_id
        self.reply_to_explicit_id = reply_to_explicit_id
        self.reply_to_current = reply_to_current
        self.has_audio_tag = has_audio_tag
        self.has_reply_tag = has_reply_tag

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "text": self.text,
            "audioAsVoice": self.audio_as_voice,
            "replyToCurrent": self.reply_to_current,
            "hasAudioTag": self.has_audio_tag,
            "hasReplyTag": self.has_reply_tag,
        }
        if self.reply_to_id is not None:
            out["replyToId"] = self.reply_to_id
        if self.reply_to_explicit_id is not None:
            out["replyToExplicitId"] = self.reply_to_explicit_id
        return out


class DisplayMessageWithContent:
    """Lightweight wrapper around a transcript message with a content array."""

    def __init__(self, content: Any = None) -> None:
        self.content = content

    def to_dict(self) -> Dict[str, Any]:
        return {"content": self.content}


def _replacement_preserves_word_boundary(source: str, offset: int, length: int) -> str:
    before = source[offset - 1] if offset > 0 else ""
    after = source[offset + length] if offset + length < len(source) else ""
    if before and after and not before.isspace() and not after.isspace():
        return " "
    return ""


def _normalize_optional_string(value: Any) -> Optional[str]:
    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned or None
    return None


def _normalize_directive_whitespace(text: str) -> str:
    if not text:
        return text
    return (
        text.replace("\r\n", "\n")
        .replace("  ", " ")
        .replace("\t", " ")
    )


def strip_inline_directive_tags_for_display(text: str) -> Dict[str, Any]:
    """Strip inline audio/reply directive tags from text used for display.

    Mirrors :func:`stripInlineDirectiveTagsForDisplay` (``utils/directive-tags.ts``).
    """
    if not text:
        return {"text": text, "changed": False}
    without_audio = _AUDIO_TAG_RE.sub("", text)
    stripped = _REPLY_TAG_RE.sub("", without_audio)
    return {"text": stripped, "changed": stripped != text}


def _strip_unsafe_reply_directive_chars(value: str) -> str:
    out: List[str] = []
    for ch in value:
        code = ord(ch)
        if (0 <= code <= 31) or code == 127 or (0x80 <= code <= 0x9F) or ch in ("[", "]"):
            continue
        out.append(ch)
    return "".join(out)


def sanitize_reply_directive_id(raw_reply_to_id: Optional[str]) -> Optional[str]:
    """Sanitize an explicit reply-to directive id.

    Mirrors :func:`sanitizeReplyDirectiveId` (``utils/directive-tags.ts``).
    """
    if not isinstance(raw_reply_to_id, str):
        return None
    trimmed = raw_reply_to_id.strip()
    if not trimmed:
        return None
    sanitized = _strip_unsafe_reply_directive_chars(trimmed).strip()
    if not sanitized:
        return None
    chars = list(sanitized)
    if len(chars) > MAX_REPLY_DIRECTIVE_ID_LENGTH:
        return "".join(chars[:MAX_REPLY_DIRECTIVE_ID_LENGTH])
    return sanitized


def strip_inline_directive_tags_for_delivery(text: str) -> Dict[str, Any]:
    """Strip inline directive tags with whitespace preservation for delivery.

    Mirrors :func:`stripInlineDirectiveTagsForDelivery`
    (``utils/directive-tags.ts``).
    """
    if not text:
        return {"text": text, "changed": False}
    stripped = _INLINE_DIRECTIVE_TAG_WITH_PADDING_RE.sub(" ", text)
    changed = stripped != text
    return {
        "text": stripped.strip() if changed else text,
        "changed": changed,
    }


def _is_message_text_part(part: Any) -> bool:
    if not isinstance(part, dict):
        return False
    return part.get("type") == "text" and isinstance(part.get("text"), str)


def strip_inline_directive_tags_from_message_for_display(
    message: Any,
) -> Any:
    """Strip inline directive tags from a transcript message while preserving shape.

    Mirrors :func:`stripInlineDirectiveTagsFromMessageForDisplay`
    (``utils/directive-tags.ts``).
    """
    if not message or not isinstance(message, dict):
        return message
    content = message.get("content")
    if not isinstance(content, list):
        return message
    cleaned: Optional[List[Any]] = None
    for i, part in enumerate(content):
        next_part: Any = part
        if isinstance(part, dict) and _is_message_text_part(part):
            stripped = strip_inline_directive_tags_for_display(part.get("text", ""))
            if stripped.get("changed"):
                next_part = {**part, "text": stripped["text"]}
        if next_part is part and cleaned is not None:
            cleaned.append(part)
            continue
        if cleaned is None:
            cleaned = content[:i]
        if next_part is not part:
            cleaned.append(next_part)
        else:
            cleaned.append(part)
    if cleaned is None:
        return message
    return {**message, "content": cleaned}


def parse_inline_directives(
    text: Optional[str] = None,
    options: Optional[Dict[str, Any]] = None,
) -> InlineDirectiveParseResult:
    """Parse inline audio/reply directives from user text.

    Mirrors :func:`parseInlineDirectives` (``utils/directive-tags.ts``).
    """
    options = options or {}
    current_message_id = options.get("currentMessageId")
    strip_audio_tag = options.get("stripAudioTag", True)
    strip_reply_tags = options.get("stripReplyTags", True)
    if not text:
        return InlineDirectiveParseResult()
    if "[[" not in text:
        return InlineDirectiveParseResult(
            text=_normalize_directive_whitespace(text),
        )

    cleaned = text
    audio_as_voice = False
    has_audio_tag = False
    has_reply_tag = False
    saw_current = False
    last_explicit_id: Optional[str] = None

    def _audio_replace(match: re.Match) -> str:
        nonlocal audio_as_voice, has_audio_tag
        audio_as_voice = True
        has_audio_tag = True
        return "" if strip_audio_tag else match.group(0)

    def _reply_replace(match: re.Match) -> str:
        nonlocal has_reply_tag, saw_current, last_explicit_id
        has_reply_tag = True
        id_raw = match.group(1)
        if id_raw is None:
            saw_current = True
        else:
            id_clean = sanitize_reply_directive_id(id_raw)
            if id_clean:
                last_explicit_id = id_clean
        return "" if strip_reply_tags else match.group(0)

    cleaned = _AUDIO_TAG_RE.sub(_audio_replace, cleaned)
    cleaned = _REPLY_TAG_RE.sub(_reply_replace, cleaned)
    cleaned = _normalize_directive_whitespace(cleaned)
    reply_to_id = last_explicit_id
    if reply_to_id is None and saw_current:
        reply_to_id = _normalize_optional_string(current_message_id)
    return InlineDirectiveParseResult(
        text=cleaned,
        audio_as_voice=audio_as_voice,
        reply_to_id=reply_to_id,
        reply_to_explicit_id=last_explicit_id,
        reply_to_current=saw_current,
        has_audio_tag=has_audio_tag,
        has_reply_tag=has_reply_tag,
    )


__all__ = [
    "MAX_REPLY_DIRECTIVE_ID_LENGTH",
    "InlineDirectiveParseResult",
    "DisplayMessageWithContent",
    "strip_inline_directive_tags_for_display",
    "strip_inline_directive_tags_for_delivery",
    "strip_inline_directive_tags_from_message_for_display",
    "sanitize_reply_directive_id",
    "parse_inline_directives",
]
