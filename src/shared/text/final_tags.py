"""jarvis.shared.text.final_tags — final-answer tag detector.

OpenClaw parity: mirrors ``openclaw-main/src/shared/text/final-tags.ts``.
"""
from __future__ import annotations

import re
from typing import List, Optional, TypedDict


class FinalTagMatch(TypedDict):
    index: int
    text: str
    isClose: bool
    isSelfClosing: bool


_FINAL_TAG_CANDIDATE_RE = re.compile(r"<[^<>]*>")


def _is_whitespace(ch: str) -> bool:
    return ch.isspace()


def _parse_attribute_list(text: str) -> bool:
    """Parse a possibly-empty attribute list. Returns True on success."""
    index = 0
    while index < len(text):
        while index < len(text) and _is_whitespace(text[index]):
            index += 1
        if index >= len(text):
            return True
        name_start = index
        while index < len(text):
            ch = text[index]
            if _is_whitespace(ch) or ch == "=":
                break
            if ch in ('/', '"', "'", "<", ">"):
                return False
            index += 1
        if index == name_start:
            return False
        while index < len(text) and _is_whitespace(text[index]):
            index += 1
        if index >= len(text) or text[index] != "=":
            continue
        index += 1
        while index < len(text) and _is_whitespace(text[index]):
            index += 1
        if index >= len(text):
            return False
        quote = text[index]
        if quote in ('"', "'"):
            index += 1
            end = text.find(quote, index)
            if end == -1:
                return False
            index = end + 1
            continue
        value_start = index
        while index < len(text) and not _is_whitespace(text[index]):
            ch = text[index]
            if ch in ('"', "'", "<", ">"):
                return False
            index += 1
        if index == value_start:
            return False
    return True


def _parse_final_tag(text: str) -> Optional[dict]:
    if not text.startswith("<") or not text.endswith(">"):
        return None
    body = text[1:-1].lstrip()
    is_close = False
    if body.startswith("/"):
        is_close = True
        body = body[1:].lstrip()
    if not body.lower().startswith("final"):
        return None
    boundary = body[5:6] or ""
    if boundary and not _is_whitespace(boundary) and boundary != "/":
        return None
    rest = body[5:]
    if is_close:
        return {"isClose": True, "isSelfClosing": False} if rest.strip() == "" else None
    trimmed_rest = rest.rstrip()
    is_self_closing = trimmed_rest.endswith("/")
    rest = trimmed_rest[:-1] if is_self_closing else rest
    if not _parse_attribute_list(rest):
        return None
    return {"isClose": False, "isSelfClosing": is_self_closing}


def find_final_tag_matches(text: str) -> List[FinalTagMatch]:
    """Find valid ``<final>`` control tags in ``text``.

    Mirrors :func:`findFinalTagMatches` (``shared/text/final-tags.ts``).
    """
    if not isinstance(text, str):
        return []
    out: List[FinalTagMatch] = []
    for match in _FINAL_TAG_CANDIDATE_RE.finditer(text):
        tag_text = match.group(0)
        parsed = _parse_final_tag(tag_text)
        if not parsed:
            continue
        out.append({
            "index": match.start() or 0,
            "text": tag_text,
            "isClose": parsed["isClose"],
            "isSelfClosing": parsed["isSelfClosing"],
        })
    return out


def strip_final_tags(text: str) -> str:
    """Remove valid ``<final>`` tags while preserving enclosed visible text.

    Mirrors :func:`stripFinalTags` (``shared/text/final-tags.ts``).
    """
    if not isinstance(text, str):
        return text
    out_parts: List[str] = []
    last = 0
    for match in find_final_tag_matches(text):
        out_parts.append(text[last:match["index"]])
        last = match["index"] + len(match["text"])
    out_parts.append(text[last:])
    return "".join(out_parts)


__all__ = ["FinalTagMatch", "find_final_tag_matches", "strip_final_tags"]
