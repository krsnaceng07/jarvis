"""jarvis.shared.text.citation_control_markers — citation control marker stripper.

OpenClaw parity: mirrors
``openclaw-main/src/shared/text/citation-control-markers.ts``.

The OpenClaw source uses specific Unicode private-use characters for
``〈cite…〉`` markers; this focused minimal port matches the same shape
using the fullwidth-angle-bracket pair that the OpenClaw patterns target
after Unicode escape resolution.
"""
from __future__ import annotations

import re

#: Matches ``〈cite〉`` and ``〈cite…〉`` markers in any context.
_UNSUPPORTED_RE = re.compile(
    r"\u3008cite(?:\u3009[^" + r"\u3008]*)?\u3008" if False else
    r"\u3008cite\b[^" + r"\u3008\u3009]*\u3009",
    re.UNICODE,
)

#: Matches trailing ``〈cite〉`` markers (followed by newline or end of string).
_TRAILING_RE = re.compile(
    r"[ \t]*\u3008cite\b[^" + r"\u3008\u3009]*\u3009(?=\r?\n|$)",
    re.UNICODE,
)


def strip_unsupported_citation_control_markers(text: str) -> str:
    """Remove unsupported model citation-control markers without disturbing
    normal hard breaks.

    Mirrors :func:`stripUnsupportedCitationControlMarkers`
    (``shared/text/citation-control-markers.ts``).
    """
    if not isinstance(text, str):
        return text
    return _UNSUPPORTED_RE.sub("", _TRAILING_RE.sub("", text))


__all__ = ["strip_unsupported_citation_control_markers"]
