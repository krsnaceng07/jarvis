"""Canonical conversation and target resolution for channels.

Mirrors OpenClaw's ``src/channels/conversation-resolution.ts``.

Features:
- Normalizes channel targets, stripping transport prefixes (``user:``, ``spaces/``, ``group:``).
- Separates base conversation ID from thread / topic qualifiers (``:thread:<id>``, ``:topic:<id>``).
- Derives canonical, process-stable session keys across platforms:
  ``agent:<agentId>:<channelId>:<peerKind>:<peerId>[:thread:<threadId>]``.
- Handles thread parent fallbacks cleanly.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

CANONICAL_TARGET_PREFIXES: tuple[str, ...] = (
    "user:",
    "spaces/",
    "group:",
    "channel:",
)

THREAD_SUFFIX_PATTERN = re.compile(r":(?:thread|topic):([a-zA-Z0-9_\-\.]+)\Z")


@dataclass(frozen=True, slots=True)
class ConversationResolution:
    """Canonical representation of an identified conversation target."""

    channel_id: str
    conversation_id: str
    session_key: str
    peer_kind: str = "user"  # "user" | "group" | "channel"
    peer_id: str = ""
    thread_id: str | None = None
    parent_conversation_id: str | None = None
    account_id: str | None = None


def strip_target_prefix(target: str | None) -> str:
    """Strip standard routing prefixes like 'user:' or 'spaces/'."""
    if not target:
        return ""
    cleaned = target.strip()
    for prefix in CANONICAL_TARGET_PREFIXES:
        if cleaned.lower().startswith(prefix):
            return cleaned[len(prefix) :].strip()
    return cleaned


def extract_thread_qualifier(target: str | None) -> tuple[str, str | None]:
    """Extract thread/topic qualifier from a conversation target string.

    Example: ``"12345:thread:987"`` -> ``("12345", "987")``
    """
    if not target:
        return "", None

    cleaned = target.strip()
    match = THREAD_SUFFIX_PATTERN.search(cleaned)
    if match:
        base_id = cleaned[: match.start()].strip()
        thread_id = match.group(1).strip()
        return base_id, thread_id

    return cleaned, None


def derive_canonical_session_key(
    channel_id: str,
    peer_id: str,
    peer_kind: str = "user",
    thread_id: str | None = None,
    agent_id: str = "default",
) -> str:
    """Derive canonical OpenClaw-parity session key."""
    norm_chan = channel_id.strip().lower() or "default"
    norm_peer = strip_target_prefix(peer_id).strip().lower() or "unknown"
    norm_kind = peer_kind.strip().lower() or "user"
    norm_agent = agent_id.strip().lower() or "default"

    base_key = f"agent:{norm_agent}:{norm_chan}:{norm_kind}:{norm_peer}"
    if thread_id and str(thread_id).strip():
        return f"{base_key}:thread:{str(thread_id).strip()}"
    return base_key


def resolve_canonical_conversation(
    channel_id: str,
    conversation_id: str,
    peer_kind: str = "user",
    peer_id: str | None = None,
    thread_id: str | None = None,
    parent_conversation_id: str | None = None,
    account_id: str | None = None,
    agent_id: str = "default",
) -> ConversationResolution:
    """Resolve full conversation details and canonical session key."""
    base_conv, extracted_thread = extract_thread_qualifier(conversation_id)
    effective_thread = thread_id or extracted_thread
    effective_peer_id = peer_id or strip_target_prefix(base_conv)

    session_key = derive_canonical_session_key(
        channel_id=channel_id,
        peer_id=effective_peer_id,
        peer_kind=peer_kind,
        thread_id=effective_thread,
        agent_id=agent_id,
    )

    return ConversationResolution(
        channel_id=channel_id.strip().lower(),
        conversation_id=base_conv,
        session_key=session_key,
        peer_kind=peer_kind.strip().lower(),
        peer_id=effective_peer_id,
        thread_id=effective_thread,
        parent_conversation_id=parent_conversation_id,
        account_id=account_id,
    )


__all__ = [
    "CANONICAL_TARGET_PREFIXES",
    "ConversationResolution",
    "derive_canonical_session_key",
    "extract_thread_qualifier",
    "resolve_canonical_conversation",
    "strip_target_prefix",
]
