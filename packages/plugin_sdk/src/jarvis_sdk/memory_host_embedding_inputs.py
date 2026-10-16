"""jarvis_sdk.memory_host_embedding_inputs — embedding input shapes.

OpenClaw parity: mirrors
``packages/memory-host-sdk/src/host/embedding-inputs.ts`` (37 LOC).
Public embedding input contract for text and inline multimodal
parts. The OpenClaw source uses a discriminated union of
``text`` / ``inline-data`` parts; the Python port uses
``TypedDict`` with the same shape.

Public API:
- ``EmbeddingInputTextPart`` / ``EmbeddingInputInlineDataPart``
  TypedDicts.
- ``EmbeddingInput`` — the provider-facing envelope.
- ``build_text_embedding_input(text)`` — common text-only shape.
- ``has_non_text_embedding_parts(input)`` — true when the input
  carries multimodal ``inline-data`` parts.
"""

from __future__ import annotations

from typing import TypedDict


class EmbeddingInputTextPart(TypedDict):
    """Text part of a structured embedding input."""

    type: str
    text: str


class EmbeddingInputInlineDataPart(TypedDict):
    """Inline binary payload for multimodal embedding providers."""

    type: str
    mimeType: str  # noqa: N815 — camelCase mirrors OpenClaw JSON
    data: str


def _make_text_part(text: str) -> EmbeddingInputTextPart:
    return {"type": "text", "text": text}


def _make_inline_data_part(mime_type: str, data: str) -> EmbeddingInputInlineDataPart:
    return {"type": "inline-data", "mimeType": mime_type, "data": data}


# Helper: keep the original union semantics clear for callers.
EmbeddingInputPart = EmbeddingInputTextPart | EmbeddingInputInlineDataPart


class EmbeddingInput(TypedDict, total=False):
    """Provider-facing input while preserving the plain text fallback.

    Mirrors OpenClaw's ``EmbeddingInput``. ``parts`` is
    optional; when present, the provider may use the
    structured form (e.g. for multimodal embedding APIs).
    """

    text: str
    parts: list[EmbeddingInputPart]


def build_text_embedding_input(text: str) -> EmbeddingInput:
    """Build the common text-only embedding input shape.

    Mirrors OpenClaw's ``buildTextEmbeddingInput``.
    """
    return {"text": text}


def has_non_text_embedding_parts(input_: EmbeddingInput | None) -> bool:
    """Return ``True`` when ``input_`` needs structured provider handling.

    Mirrors OpenClaw's ``hasNonTextEmbeddingParts``. ``True``
    when the input has at least one ``inline-data`` part.
    """
    if not input_:
        return False
    parts = input_.get("parts")
    if not parts:
        return False
    return any(part.get("type") == "inline-data" for part in parts)


__all__ = [
    "EmbeddingInput",
    "EmbeddingInputTextPart",
    "EmbeddingInputInlineDataPart",
    "EmbeddingInputPart",
    "build_text_embedding_input",
    "has_non_text_embedding_parts",
    # Re-export the part constructors under the OpenClaw-ish names
    # for callers that prefer the factory form. They are not part of
    # the public TS surface; included as a convenience.
    "_make_text_part",
    "_make_inline_data_part",
]
