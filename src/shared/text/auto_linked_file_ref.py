"""jarvis.shared.text.auto_linked_file_ref — auto-linked file ref detector.

OpenClaw parity: mirrors ``openclaw-main/src/shared/text/auto-linked-file-ref.ts``.
"""
from __future__ import annotations

import re

#: File extensions that count as auto-linkable file refs.
FILE_REF_EXTENSIONS = ("md", "go", "py", "pl", "sh", "am", "at", "be", "cc")

#: Set form for membership checks.
FILE_REF_EXTENSIONS_WITH_TLD = frozenset(FILE_REF_EXTENSIONS)

_HTTPS_PREFIX_RE = re.compile(r"^https?://", re.IGNORECASE)


def is_auto_linked_file_ref(href: str, label: str) -> bool:
    """Return whether ``href`` and ``label`` describe an auto-linked file ref.

    Mirrors :func:`isAutoLinkedFileRef`
    (``shared/text/auto-linked-file-ref.ts``).
    """
    if not isinstance(href, str) or not isinstance(label, str):
        return False
    stripped = _HTTPS_PREFIX_RE.sub("", href)
    if stripped != label:
        return False
    dot_index = label.rfind(".")
    if dot_index < 1:
        return False
    ext = label[dot_index + 1:].strip().lower()
    if ext not in FILE_REF_EXTENSIONS_WITH_TLD:
        return False
    segments = label.split("/")
    if len(segments) > 1:
        for segment in segments[:-1]:
            if "." in segment:
                return False
    return True


__all__ = [
    "FILE_REF_EXTENSIONS",
    "FILE_REF_EXTENSIONS_WITH_TLD",
    "is_auto_linked_file_ref",
]
