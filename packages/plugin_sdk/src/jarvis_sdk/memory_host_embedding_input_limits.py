"""jarvis_sdk.memory_host_embedding_input_limits — embedding input size helpers.

OpenClaw parity: mirrors
``packages/memory-host-sdk/src/host/embedding-input-limits.ts`` (~85 LOC).
Helpers for enforcing embedding model input size limits. We
use UTF-8 byte length as a conservative upper bound for
tokenizer output: tokenizers operate over bytes, so a token
must contain at least one byte, hence
``token_count <= utf8_byte_length``.

Public API:
- ``estimate_utf8_bytes(text)`` — UTF-8 byte length.
- ``estimate_structured_embedding_input_bytes(input)`` —
  total UTF-8 bytes for a (possibly multimodal) input.
- ``split_text_to_utf8_byte_limit(text, max_bytes)`` —
  splits ``text`` into chunks each no larger than
  ``max_bytes`` UTF-8 bytes, preserving surrogate pairs.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .memory_host_embedding_inputs import EmbeddingInput


def estimate_utf8_bytes(text: str) -> int:
    """Return the UTF-8 byte length of ``text``.

    Mirrors OpenClaw's ``estimateUtf8Bytes``. ``0`` for
    empty / falsy input.
    """
    if not text:
        return 0
    return len(text.encode("utf-8"))


def estimate_structured_embedding_input_bytes(input_: EmbeddingInput) -> int:
    """Estimate the UTF-8 byte size of a (possibly multimodal) input.

    Mirrors OpenClaw's ``estimateStructuredEmbeddingInputBytes``.
    For a text-only input, returns the UTF-8 byte length of
    the text. For a structured input, sums the bytes for each
    part (text bytes for text parts, ``mimeType + data`` bytes
    for inline-data parts).
    """
    parts = input_.get("parts")
    if not parts:
        return estimate_utf8_bytes(input_.get("text", ""))
    total = 0
    for part in parts:
        kind = part.get("type")
        if kind == "text":
            total += estimate_utf8_bytes(part.get("text", ""))
        elif kind == "inline-data":
            total += estimate_utf8_bytes(part.get("mimeType", ""))
            total += estimate_utf8_bytes(part.get("data", ""))
    return total


def split_text_to_utf8_byte_limit(
    text: str,
    max_utf8_bytes: int,
) -> list[str]:
    """Split ``text`` so each chunk is no larger than ``max_utf8_bytes``.

    Mirrors OpenClaw's ``splitTextToUtf8ByteLimit``. Uses
    binary search to find the largest split point that keeps
    the chunk under the byte budget, then advances. Avoids
    splitting inside a surrogate pair.

    When ``max_utf8_bytes <= 0`` or the whole text already
    fits, returns ``[text]``.
    """
    if max_utf8_bytes <= 0:
        return [text]
    if estimate_utf8_bytes(text) <= max_utf8_bytes:
        return [text]

    parts: list[str] = []
    cursor = 0
    text_length = len(text)
    while cursor < text_length:
        low = cursor + 1
        high = min(text_length, cursor + max_utf8_bytes)
        best = cursor
        while low <= high:
            mid = (low + high) // 2
            slice_bytes = estimate_utf8_bytes(text[cursor:mid])
            if slice_bytes <= max_utf8_bytes:
                best = mid
                low = mid + 1
            else:
                high = mid - 1
        if best <= cursor:
            best = min(text_length, cursor + 1)

        # Avoid splitting a surrogate pair.
        if (
            best < text_length
            and best > cursor
            and 0xD800 <= ord(text[best - 1]) <= 0xDBFF
            and 0xDC00 <= ord(text[best]) <= 0xDFFF
        ):
            best -= 1

        part = text[cursor:best]
        if not part:
            break
        parts.append(part)
        cursor = best
    return parts


__all__ = [
    "estimate_utf8_bytes",
    "estimate_structured_embedding_input_bytes",
    "split_text_to_utf8_byte_limit",
]
