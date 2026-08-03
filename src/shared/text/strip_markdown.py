"""jarvis.shared.text.strip_markdown — focused minimal Markdown-to-plain-text.

OpenClaw parity: mirrors ``openclaw-main/src/shared/text/strip-markdown.ts``.

The OpenClaw source delegates to ``markdown-core`` for IR parsing; this port
exposes a focused minimal surface that strips common Markdown decorations
without requiring the full IR pipeline. The contract for callers needing
IR-driven link/role-header handling is preserved as an extension point.
"""
from __future__ import annotations

import re
from typing import List, Optional, TypedDict


class StripMarkdownOptions(TypedDict, total=False):
    assistantTranscriptRoleHeaders: bool
    assistantTranscriptRolePrefix: str
    linkStyle: str  # "label" | "label-and-url"
    mode: str  # "plain-text" | "speech"


_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_HEADING_RE = re.compile(r"(?m)^#{1,6}\s+")
_BOLD_ITAL_RE = re.compile(r"[*_]{1,3}([^*_]+)[*_]{1,3}")
_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
_CODE_FENCE_RE = re.compile(r"```[\s\S]*?```")
_INLINE_CODE_RE = re.compile(r"`([^`]+)`")
_HTML_TAG_RE = re.compile(r"<[^<>]+>")
_BLOCKQUOTE_RE = re.compile(r"(?m)^>\s*")
_HR_RE = re.compile(r"(?m)^[\s>]*(?:---|\*\*\*|___)[\s<]*$")


def _clean_speech_text(text: str) -> str:
    lines = text.split("\n")
    out: List[str] = []
    for line in lines:
        s = line.strip()
        # Drop purely punctuation/symbol/whitespace lines.
        if s and re.fullmatch(r"[\W_]+", s):
            out.append("")
            continue
        cleaned = re.sub(r"^[•◦▪‣⁃]\s+", "", line)
        cleaned = re.sub(r"\.{4,}", "...", cleaned)
        cleaned = re.sub(r"([!?,;:])\1+", r"\1", cleaned)
        cleaned = re.sub(r"[ \t]{2,}", " ", cleaned).strip()
        out.append(cleaned)
    text = "\n".join(out)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def strip_markdown(text: str, options: Optional[dict] = None) -> str:
    """Strip Markdown decorations to plain text.

    Focused minimal port of :func:`stripMarkdown`
    (``shared/text/strip-markdown.ts``).
    """
    if not isinstance(text, str):
        return text
    options = options or {}
    mode = options.get("mode") or "plain-text"
    link_style = options.get("linkStyle") or "label-and-url"
    out = text
    # Drop code fences first so their content is preserved verbatim.
    if link_style == "label-and-url":
        def _link_replace(match: "re.Match[str]") -> str:
            label = match.group(1)
            href = match.group(2)
            if href and label and label != href:
                return f"{label} ({href})"
            return label
        out = _LINK_RE.sub(_link_replace, out)
    else:
        out = _LINK_RE.sub(r"\1", out)
    out = _IMAGE_RE.sub("", out)
    out = _HEADING_RE.sub("", out)
    out = _BOLD_ITAL_RE.sub(r"\1", out)
    out = _INLINE_CODE_RE.sub(r"\1", out)
    out = _CODE_FENCE_RE.sub("", out)
    out = _HTML_TAG_RE.sub("", out)
    out = _BLOCKQUOTE_RE.sub("", out)
    out = _HR_RE.sub("", out)
    out = re.sub(r"[ \t]+\n", "\n", out)
    out = re.sub(r"\n{3,}", "\n\n", out)
    if mode == "speech":
        out = _clean_speech_text(out)
    return out.strip()


__all__ = ["strip_markdown", "StripMarkdownOptions"]
