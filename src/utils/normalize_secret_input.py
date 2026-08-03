"""jarvis.utils.normalize_secret_input — normalize copy/pasted secrets.

OpenClaw parity: mirrors
``openclaw-main/src/utils/normalize-secret-input.ts``.

Public surface:

- :func:`normalize_secret_input`
- :func:`normalize_optional_secret_input`
"""
from __future__ import annotations

from typing import Optional


def normalize_secret_input(value: object) -> str:
    """Normalize a raw secret value (strips line breaks + non-Latin1 chars).

    Mirrors :func:`normalizeSecretInput` (``utils/normalize-secret-input.ts``).
    """
    if not isinstance(value, str):
        return ""
    collapsed = value.replace("\r", "").replace("\n", "").replace("\u2028", "").replace("\u2029", "")
    out_chars = []
    for ch in collapsed:
        code = ord(ch)
        is_control = (
            (0x00 <= code <= 0x1F)
            or code == 0x7F
            or (0x80 <= code <= 0x9F)
        )
        if code <= 0xFF and not is_control:
            out_chars.append(ch)
    return "".join(out_chars).strip()


def normalize_optional_secret_input(value: object) -> Optional[str]:
    """Normalize and convert empty output to ``None``.

    Mirrors :func:`normalizeOptionalSecretInput`
    (``utils/normalize-secret-input.ts``).
    """
    normalized = normalize_secret_input(value)
    return normalized or None


__all__ = [
    "normalize_secret_input",
    "normalize_optional_secret_input",
]
