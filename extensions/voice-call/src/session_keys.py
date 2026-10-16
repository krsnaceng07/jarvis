"""Session scope and storage namespace key resolution for Voice Call."""

from __future__ import annotations

from typing import Literal

from .phone_utils import normalize_e164_phone_number

VoiceCallSessionScope = Literal["per-phone", "per-call", "main"]


def resolve_voice_session_key(
    *,
    scope: VoiceCallSessionScope | str,
    agent_id: str = "main",
    phone_number: str | None = None,
    call_id: str | None = None,
    core_session_scope: str = "per-agent",
) -> str:
    """Resolve the storage session key for a telephony call according to sessionScope.

    - "per-phone": agent:<agentId>:voice:phone:<normalized_phone>
    - "per-call": agent:<agentId>:voice:call:<call_id>
    - "main": "global" if core_session_scope == "global" else f"agent:{agent_id}:main"
    """
    clean_agent = agent_id.strip() or "main"
    scope_str = str(scope).strip().lower()

    if scope_str == "main":
        if core_session_scope.strip().lower() == "global":
            return "global"
        return f"agent:{clean_agent}:main"

    if scope_str == "per-call":
        cid = call_id.strip() if call_id else "unknown"
        return f"agent:{clean_agent}:voice:call:{cid}"

    # Default: per-phone
    norm_phone = "unknown"
    if phone_number:
        try:
            norm_phone = normalize_e164_phone_number(phone_number)
        except ValueError:
            norm_phone = phone_number.strip()

    return f"agent:{clean_agent}:voice:phone:{norm_phone}"


def resolve_explicit_session_key(
    raw_key: str,
    configured_agent_id: str = "main",
    core_session_scope: str = "per-agent",
) -> str:
    """Resolve an explicit session key passed into call APIs."""
    clean_key = raw_key.strip()
    clean_agent = configured_agent_id.strip() or "main"

    if clean_key in ("global", "unknown"):
        return clean_key

    if clean_key.startswith(f"agent:{clean_agent}:"):
        if core_session_scope == "global" and clean_key == f"agent:{clean_agent}:main":
            return "global"
        return clean_key

    if clean_key.startswith("agent:"):
        # Foreign or malformed agent:* input is scoped under configured agent
        opaque_suffix = clean_key.replace(":", "_")
        return f"agent:{clean_agent}:voice:foreign:{opaque_suffix}"

    return f"agent:{clean_agent}:voice:{clean_key}"
