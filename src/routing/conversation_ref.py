"""jarvis.routing.conversation_ref — opaque conversation refs.

OpenClaw parity: mirrors ``src/routing/conversation-ref.ts``.
Hash input matches ``JSON.stringify`` byte-for-byte via
``json.dumps(..., separators=(",", ":"))``.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

_PEER_ID_KIND_PREFIX_RE = re.compile(
    r"^(user|channel|group|conversation|room|dm|thread):", re.IGNORECASE
)


def normalize_conversation_peer_id(channel: str, value: str) -> str:
    """Canonicalize an adapter target into the peer id used by inbound routing."""
    normalized = value.strip()
    channel_prefix = f"{channel.strip().lower()}:"
    if normalized.lower().startswith(channel_prefix):
        normalized = normalized[len(channel_prefix) :].strip()
    return _PEER_ID_KIND_PREFIX_RE.sub("", normalized).strip()


def build_conversation_ref(params: dict[str, Any]) -> str:
    """Build an opaque address from canonical transport identity.

    Never derived from model-session state. Params: channel, accountId,
    kind ("channel"|"direct"|"group"), peerId, parentConversationRef?,
    threadId?.
    """
    payload = json.dumps(
        [
            params["channel"],
            params["accountId"],
            params["kind"],
            params["peerId"],
            params.get("parentConversationRef") or "",
            params.get("threadId") or "",
        ],
        separators=(",", ":"),
        ensure_ascii=False,
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]
    return f"conv_{digest}"


__all__ = ["build_conversation_ref", "normalize_conversation_peer_id"]
