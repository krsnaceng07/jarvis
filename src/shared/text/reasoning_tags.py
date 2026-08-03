"""jarvis.shared.text.reasoning_tags — strip model reasoning tag blocks.

OpenClaw parity: mirrors ``openclaw-main/src/shared/text/reasoning-tags.ts``.

Focused minimal port: handles the common cases without bringing in the
markdown IR parser. Callers needing parser-driven detection should provide
their own pre-classified code regions.
"""
from __future__ import annotations

import re
from typing import List, Optional, TypedDict

from .code_regions import CodeRegion, find_code_regions, is_inside_code
from .final_tags import find_final_tag_matches

ReasoningTagMode = str  # "strict" | "preserve"
ReasoningTagTrim = str  # "none" | "start" | "both"
ReasoningTagScope = str  # "all" | "leading"


_QUICK_TAG_RE = re.compile(
    r"<\s*/?\s*(?:(?:antml:|mm:)?(?:think(?:ing)?|thought)|antthinking|final)\b",
    re.IGNORECASE,
)
_THINKING_TAG_RE = re.compile(
    r"<\s*(/?)\s*(?:(?:antml:|mm:)?(?:think(?:ing)?|thought)|antthinking)\b[^<>]*>",
    re.IGNORECASE,
)


def _apply_trim(value: str, mode: str) -> str:
    if mode == "none":
        return value
    if mode == "start":
        return value.lstrip()
    return value.strip()


def has_orphan_reasoning_close_boundary(params: dict) -> bool:
    """Detect a stray reasoning close tag separating two visible regions.

    Mirrors :func:`hasOrphanReasoningCloseBoundary`
    (``shared/text/reasoning-tags.ts``).
    """
    before = (params.get("before") or "").strip()
    after = (params.get("after") or "").strip()
    return bool(before) and bool(after)


def _has_reasoning_close_tag_after(
    text: str, start: int, code_regions: List[CodeRegion]
) -> bool:
    for match in _THINKING_TAG_RE.finditer(text, start):
        idx = match.start() or 0
        if is_inside_code(idx, code_regions):
            continue
        if match.group(1) == "/":
            return True
    return False


def strip_reasoning_tags_from_text(
    text: str,
    *,
    mode: str = "strict",
    trim: str = "both",
    scope: str = "all",
) -> str:
    """Strip model reasoning/final tags from visible text.

    Mirrors :func:`stripReasoningTagsFromText`
    (``shared/text/reasoning-tags.ts``).
    """
    if not text:
        return text
    if not _QUICK_TAG_RE.search(text):
        return text

    cleaned = text
    matches = find_final_tag_matches(cleaned)
    has_thinking_tag = bool(_THINKING_TAG_RE.search(cleaned))
    if not matches and not has_thinking_tag:
        return text

    if matches:
        pre_code = find_code_regions(cleaned)
        final_matches: List[dict] = []
        for match in matches:
            final_matches.append({
                "start": match["index"],
                "length": len(match["text"]),
                "inCode": is_inside_code(match["index"], pre_code),
            })
        for m in reversed(final_matches):
            if not m["inCode"]:
                cleaned = cleaned[:m["start"]] + cleaned[m["start"] + m["length"]:]

    code_regions = find_code_regions(cleaned)
    result_parts: List[str] = []
    last_index = 0
    thinking_depth = 0
    first_unclosed_content_index: Optional[int] = None

    for match in _THINKING_TAG_RE.finditer(cleaned):
        idx = match.start() or 0
        is_close = match.group(1) == "/"
        if is_inside_code(idx, code_regions):
            continue
        if thinking_depth == 0:
            if (
                scope == "leading"
                and not is_close
                and (("".join(result_parts) + cleaned[last_index:idx]).strip())
                and not _has_reasoning_close_tag_after(cleaned, idx + len(match.group(0)), code_regions)
            ):
                return _apply_trim("".join(result_parts) + cleaned[last_index:], trim)
            if is_close:
                after_index = idx + len(match.group(0))
                before = cleaned[last_index:idx]
                after = cleaned[after_index:]
                if has_orphan_reasoning_close_boundary({"before": before, "after": after}):
                    result_parts = []
                else:
                    result_parts.append(before)
                last_index = after_index
                continue
            result_parts.append(cleaned[last_index:idx])
            thinking_depth = 1
            first_unclosed_content_index = idx + len(match.group(0))
        elif is_close:
            thinking_depth -= 1
            if thinking_depth == 0:
                first_unclosed_content_index = None
        else:
            thinking_depth += 1
        last_index = idx + len(match.group(0))

    if thinking_depth == 0 or mode == "preserve":
        result_parts.append(cleaned[last_index:])

    result = "".join(result_parts)
    trimmed_result = _apply_trim(result, trim)
    if (
        mode == "strict"
        and thinking_depth > 0
        and not trimmed_result
        and first_unclosed_content_index is not None
        and cleaned.strip()
    ):
        return _apply_trim(cleaned[first_unclosed_content_index:], trim)
    return trimmed_result


__all__ = [
    "ReasoningTagMode",
    "ReasoningTagTrim",
    "ReasoningTagScope",
    "has_orphan_reasoning_close_boundary",
    "strip_reasoning_tags_from_text",
]
