"""jarvis.config.silent_reply — silent-reply config normalization.

OpenClaw parity: mirrors ``openclaw-main/src/config/silent-reply.ts``.

Focused minimal port: thin facade that defers to the shared silent-reply
policy helpers in ``src/shared/silent_reply_policy.py``.
"""
from __future__ import annotations

from typing import Optional

from src.shared.silent_reply_policy import (
    DEFAULT_SILENT_REPLY_POLICY,
    SilentReplyConversationType,
    SilentReplyPolicy,
    classify_silent_reply_conversation_type,
    resolve_silent_reply_policy_from_policies,
)


def _resolve_context(params: dict) -> dict:
    cfg = params.get("cfg") or {}
    surface = (params.get("surface") or "").strip().lower() if isinstance(params.get("surface"), str) else ""
    surface_block = cfg.get("surfaces", {}).get(surface) if surface else None
    return {
        "conversationType": classify_silent_reply_conversation_type({
            "sessionKey": params.get("sessionKey"),
            "surface": surface,
            "conversationType": params.get("conversationType"),
        }),
        "defaultPolicy": (cfg.get("agents") or {}).get("defaults", {}).get("silentReply"),
        "surfacePolicy": (surface_block or {}).get("silentReply") if isinstance(surface_block, dict) else None,
    }


def resolve_silent_reply_settings(params: dict) -> dict:
    """Resolve the effective silent-reply settings for a routed conversation.

    Mirrors :func:`resolveSilentReplySettings`
    (``shared/config/silent-reply.ts`).
    """
    context = _resolve_context(params)
    return {
        "policy": resolve_silent_reply_policy_from_policies(context),
    }


def resolve_silent_reply_policy(params: dict) -> SilentReplyPolicy:
    """Return just the effective silent-reply policy."""
    return resolve_silent_reply_settings(params)["policy"]


__all__ = [
    "resolve_silent_reply_settings",
    "resolve_silent_reply_policy",
]
