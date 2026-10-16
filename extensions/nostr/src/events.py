"""Nostr event serialization, ID hashing, and data classes."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class NostrEvent:
    pubkey: str
    created_at: int
    kind: int
    tags: list[list[str]] = field(default_factory=list)
    content: str = ""
    sig: str = ""
    id: str = ""

    def compute_id(self) -> str:
        """Compute SHA-256 hash of serialized event array [0, pubkey, created_at, kind, tags, content]."""
        serialized = json.dumps(
            [0, self.pubkey, self.created_at, self.kind, self.tags, self.content],
            separators=(",", ":"),
            ensure_ascii=False,
        )
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        event_id = self.id or self.compute_id()
        return {
            "id": event_id,
            "pubkey": self.pubkey,
            "created_at": self.created_at,
            "kind": self.kind,
            "tags": self.tags,
            "content": self.content,
            "sig": self.sig,
        }


def create_text_note(pubkey: str, content: str, tags: list[list[str]] | None = None) -> NostrEvent:
    """Create a kind 1 Nostr text note."""
    ev = NostrEvent(
        pubkey=pubkey,
        created_at=int(time.time()),
        kind=1,
        tags=tags or [],
        content=content,
    )
    ev.id = ev.compute_id()
    return ev


def create_direct_message(
    sender_pubkey: str,
    recipient_pubkey: str,
    content: str,
) -> NostrEvent:
    """Create a kind 4 Nostr encrypted direct message (with 'p' tag)."""
    ev = NostrEvent(
        pubkey=sender_pubkey,
        created_at=int(time.time()),
        kind=4,
        tags=[["p", recipient_pubkey]],
        content=content,
    )
    ev.id = ev.compute_id()
    return ev
