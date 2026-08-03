"""jarvis.shared.transcript_only_openclaw_assistant — assistant transcript predicates.

OpenClaw parity: mirrors
``openclaw-main/src/shared/transcript-only-openclaw-assistant.ts``.
"""
from __future__ import annotations

from typing import Any, Set

OPENCLAW_TRANSCRIPT_ARTIFACT_API = "openclaw-transcript"
OPENCLAW_TRANSCRIPT_ARTIFACT_PROVIDER = "openclaw"
OPENCLAW_DELIVERY_MIRROR_MODEL = "delivery-mirror"
_OPENCLAW_GATEWAY_INJECTED_MODEL = "gateway-injected"

_TRANSCRIPT_ONLY_OPENCLAW_ASSISTANT_MODELS: Set[str] = {
    OPENCLAW_DELIVERY_MIRROR_MODEL,
    _OPENCLAW_GATEWAY_INJECTED_MODEL,
}

_OPENCLAW_DELIVERY_MIRROR_KINDS: Set[str] = {
    "channel-final",
    "channel-final-suppressed",
    "message-tool-source-reply",
}


def _is_openclaw_delivery_mirror_marker(value: Any) -> bool:
    if not value or not isinstance(value, dict) or isinstance(value, list):
        return False
    kind = value.get("kind")
    return isinstance(kind, str) and kind in _OPENCLAW_DELIVERY_MIRROR_KINDS


def is_transcript_only_openclaw_assistant_model(provider: Any, model: Any) -> bool:
    """Return whether the model is an OpenClaw transcript-only assistant model.

    Mirrors :func:`isTranscriptOnlyOpenClawAssistantModel`
    (``shared/transcript-only-openclaw-assistant.ts``).
    """
    return (
        provider == OPENCLAW_TRANSCRIPT_ARTIFACT_PROVIDER
        and isinstance(model, str)
        and model in _TRANSCRIPT_ONLY_OPENCLAW_ASSISTANT_MODELS
    )


def is_transcript_only_openclaw_assistant_message(message: Any) -> bool:
    """Return whether the message is an OpenClaw-authored transcript artifact.

    Mirrors :func:`isTranscriptOnlyOpenClawAssistantMessage`
    (``shared/transcript-only-openclaw-assistant.ts``).
    """
    if not message or not isinstance(message, dict) or isinstance(message, list):
        return False
    role = message.get("role")
    if role != "assistant":
        return False
    if is_transcript_only_openclaw_assistant_model(
        message.get("provider"), message.get("model")
    ):
        return True
    return _is_openclaw_delivery_mirror_marker(message.get("openclawDeliveryMirror"))


def is_openclaw_message_tool_mirror_assistant_message(message: Any) -> bool:
    """Return whether the message is an OpenClaw message-tool mirror.

    Mirrors :func:`isOpenClawMessageToolMirrorAssistantMessage`
    (``shared/transcript-only-openclaw-assistant.ts``).
    """
    if not message or not isinstance(message, dict) or isinstance(message, list):
        return False
    return (
        message.get("role") == "assistant"
        and message.get("openclawMessageToolMirror") is not None
    )


def is_openclaw_internal_source_reply_mirror_assistant_message(message: Any) -> bool:
    """Return whether the message is an internal-source-reply mirror.

    Mirrors :func:`isOpenClawInternalSourceReplyMirrorAssistantMessage`
    (``shared/transcript-only-openclaw-assistant.ts``).
    """
    if not is_openclaw_message_tool_mirror_assistant_message(message):
        return False
    marker = message.get("openclawMessageToolMirror")
    if not marker or not isinstance(marker, dict) or isinstance(marker, list):
        return False
    return marker.get("sourceReplySink") == "internal-ui"


def is_openclaw_delivery_mirror_assistant_message(message: Any) -> bool:
    """Return whether the message is an OpenClaw delivery-mirror assistant row.

    Mirrors :func:`isOpenClawDeliveryMirrorAssistantMessage`
    (``shared/transcript-only-openclaw-assistant.ts``).
    """
    if not message or not isinstance(message, dict) or isinstance(message, list):
        return False
    return (
        message.get("role") == "assistant"
        and message.get("provider") == OPENCLAW_TRANSCRIPT_ARTIFACT_PROVIDER
        and message.get("model") == OPENCLAW_DELIVERY_MIRROR_MODEL
    )


__all__ = [
    "OPENCLAW_TRANSCRIPT_ARTIFACT_API",
    "OPENCLAW_TRANSCRIPT_ARTIFACT_PROVIDER",
    "OPENCLAW_DELIVERY_MIRROR_MODEL",
    "is_transcript_only_openclaw_assistant_model",
    "is_transcript_only_openclaw_assistant_message",
    "is_openclaw_message_tool_mirror_assistant_message",
    "is_openclaw_internal_source_reply_mirror_assistant_message",
    "is_openclaw_delivery_mirror_assistant_message",
]
