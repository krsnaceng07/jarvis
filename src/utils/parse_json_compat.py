"""jarvis.utils.parse_json_compat — JSON parser with JSON5 fallback.

OpenClaw parity: mirrors ``openclaw-main/src/utils/parse-json-compat.ts``.

Public surface:

- :func:`parse_json_with_json5_fallback`
"""
from __future__ import annotations

import json
import re
from typing import Any, Callable, Optional


# Minimal JSON5-ish fallback (only what we need: trailing commas + comments).
_TRAILING_COMMA = re.compile(r",\s*([}\]])")


def _strip_json5_comments_and_trailing_commas(text: str) -> str:
    out = []
    i = 0
    in_string = False
    string_quote = ""
    while i < len(text):
        ch = text[i]
        if in_string:
            out.append(ch)
            if ch == "\\" and i + 1 < len(text):
                out.append(text[i + 1])
                i += 2
                continue
            if ch == string_quote:
                in_string = False
            i += 1
            continue
        if ch in ('"', "'"):
            in_string = True
            string_quote = ch
            out.append(ch)
            i += 1
            continue
        if ch == "/" and i + 1 < len(text) and text[i + 1] == "/":
            while i < len(text) and text[i] != "\n":
                i += 1
            continue
        if ch == "/" and i + 1 < len(text) and text[i + 1] == "*":
            i += 2
            while i + 1 < len(text) and not (text[i] == "*" and text[i + 1] == "/"):
                i += 1
            i += 2
            continue
        out.append(ch)
        i += 1
    cleaned = "".join(out)
    cleaned = _TRAILING_COMMA.sub(r"\1", cleaned)
    return cleaned


def parse_json_with_json5_fallback(
    raw: str,
    json5: Optional[Callable[[str], Any]] = None,
) -> Any:
    """Parse strict JSON first, then accept JSON5 syntax (comments, trailing commas).

    Mirrors :func:`parseJsonWithJson5Fallback`
    (``utils/parse-json-compat.ts``).
    """
    try:
        return json.loads(raw)
    except Exception:
        if json5 is not None:
            return json5(raw)
        return json.loads(_strip_json5_comments_and_trailing_commas(raw), strict=False)


__all__ = ["parse_json_with_json5_fallback"]
