"""jarvis_learning.knowledge — durable semantic knowledge store.

Knowledge learning is Track 1: facts, documentation, user preferences,
API information, concept definitions.  Each entry has a source,
confidence, validation state, and optional expiration.  Entries are
never blindly saved from conversation — they require validated input.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Literal

from .experience import generate_id, now_ms

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class KnowledgeEntry:
    """A single piece of durable knowledge."""

    id: str
    created_at: int
    updated_at: int
    content: str
    source: str
    confidence: float = 0.5
    validation_state: Literal["validated", "unvalidated", "disputed", "expired"] = "unvalidated"
    expires_at: int = 0  # 0 = never expires
    category: str = ""
    tags: tuple[str, ...] = ()

    @property
    def is_expired(self) -> bool:
        if self.expires_at == 0:
            return False
        return now_ms() > self.expires_at

    @property
    def is_trustworthy(self) -> bool:
        return (
            self.validation_state == "validated" and self.confidence >= 0.5 and not self.is_expired
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "content": self.content,
            "source": self.source,
            "confidence": self.confidence,
            "validation_state": self.validation_state,
            "expires_at": self.expires_at,
            "category": self.category,
            "tags": json.dumps(list(self.tags)),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> KnowledgeEntry:
        tags = data.get("tags", "[]")
        if isinstance(tags, str):
            tags = json.loads(tags)
        return cls(
            id=data["id"],
            created_at=data["created_at"],
            updated_at=data["updated_at"],
            content=data["content"],
            source=data.get("source", "unknown"),
            confidence=float(data.get("confidence", 0.5)),
            validation_state=data.get("validation_state", "unvalidated"),
            expires_at=data.get("expires_at", 0),
            category=data.get("category", ""),
            tags=tuple(tags),
        )


class KnowledgeStore:
    """In-memory knowledge store with deduplication and validation."""

    def __init__(self) -> None:
        self._entries: dict[str, KnowledgeEntry] = {}

    def add(self, entry: KnowledgeEntry) -> KnowledgeEntry:
        """Add or merge a knowledge entry.

        If an entry with matching content already exists, the
        confidence and validation state are merged rather than
        creating a duplicate.
        """
        existing = self._find_duplicate(entry.content)
        if existing is not None:
            merged = KnowledgeEntry(
                id=existing.id,
                created_at=existing.created_at,
                updated_at=now_ms(),
                content=existing.content,
                source=f"{existing.source}; {entry.source}",
                confidence=min(1.0, max(existing.confidence, entry.confidence)),
                validation_state=(
                    "validated"
                    if entry.validation_state == "validated"
                    or existing.validation_state == "validated"
                    else existing.validation_state
                ),
                expires_at=max(existing.expires_at, entry.expires_at),
                category=entry.category or existing.category,
                tags=tuple(set(existing.tags) | set(entry.tags)),
            )
            self._entries[merged.id] = merged
            logger.debug("knowledge merged: id=%s", merged.id)
            return merged

        self._entries[entry.id] = entry
        logger.debug("knowledge added: id=%s", entry.id)
        return entry

    def get(self, entry_id: str) -> KnowledgeEntry | None:
        return self._entries.get(entry_id)

    def search(self, query: str) -> list[KnowledgeEntry]:
        """Simple keyword search (case-insensitive substring)."""
        query_lower = query.lower()
        return sorted(
            [
                e
                for e in self._entries.values()
                if query_lower in e.content.lower() and not e.is_expired
            ],
            key=lambda e: e.confidence,
            reverse=True,
        )

    def get_validated(self) -> list[KnowledgeEntry]:
        """Return only validated, non-expired entries."""
        return [e for e in self._entries.values() if e.is_trustworthy]

    def create_entry(
        self,
        content: str,
        source: str,
        *,
        confidence: float = 0.5,
        validation_state: str = "unvalidated",
        category: str = "",
        tags: tuple[str, ...] = (),
        expires_at: int = 0,
    ) -> KnowledgeEntry:
        """Create and store a new knowledge entry."""
        ts = now_ms()
        entry = KnowledgeEntry(
            id=generate_id(),
            created_at=ts,
            updated_at=ts,
            content=content,
            source=source,
            confidence=confidence,
            validation_state=validation_state,
            category=category,
            tags=tags,
            expires_at=expires_at,
        )
        return self.add(entry)

    def all_entries(self) -> list[KnowledgeEntry]:
        return list(self._entries.values())

    def load(self, entries: list[KnowledgeEntry]) -> None:
        for e in entries:
            self._entries[e.id] = e
        logger.info("loaded %d knowledge entries", len(entries))

    def _find_duplicate(self, content: str) -> KnowledgeEntry | None:
        """Find an existing entry with matching content (exact match)."""
        content_lower = content.lower().strip()
        for entry in self._entries.values():
            if entry.content.lower().strip() == content_lower:
                return entry
        return None
