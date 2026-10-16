"""State tracking and persistence for IMAP watcher cursors, claims, and message IDs."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass(slots=True)
class ImapCursor:
    uid_validity: str
    last_seen_uid: int
    updated_at: float


@dataclass(slots=True)
class ImapClaim:
    account_id: str
    uid: int
    recorded_at: float


@dataclass(slots=True)
class ImapAttempt:
    count: int
    reason: str


@dataclass(slots=True)
class ImapMessageRing:
    message_ids: list[str] = field(default_factory=list)


class InMemoryStore:
    """Lightweight in-memory store supporting register, lookup, register_if_absent, and delete."""

    def __init__(self, max_entries: int = 1000) -> None:
        self.max_entries = max_entries
        self._entries: dict[str, Any] = {}

    async def lookup(self, key: str) -> Any:
        return self._entries.get(key)

    async def register(self, key: str, value: Any) -> None:
        self._entries[key] = value

    async def register_if_absent(self, key: str, value: Any) -> bool:
        if key in self._entries:
            return False
        self._entries[key] = value
        return True

    async def delete(self, key: str) -> bool:
        return self._entries.pop(key, None) is not None


class ImapWatcherState:
    def __init__(self, runtime: Any = None) -> None:
        if runtime and hasattr(runtime, "state") and hasattr(runtime.state, "open_keyed_store"):
            self.cursors = runtime.state.open_keyed_store("cursor")
            self.claims = runtime.state.open_keyed_store("dispatch-claim")
            self.message_ids = runtime.state.open_keyed_store("msgid-ring")
            self.skips = runtime.state.open_keyed_store("skip-count")
        else:
            self.cursors = InMemoryStore(max_entries=256)
            self.claims = InMemoryStore(max_entries=20_000)
            self.message_ids = InMemoryStore(max_entries=256)
            self.skips = InMemoryStore(max_entries=2_048)


def create_imap_state(runtime: Any = None) -> ImapWatcherState:
    return ImapWatcherState(runtime)


async def initialize_imap_cursor(
    state: ImapWatcherState,
    account_id: str,
    uid_validity: str,
    uid_next: int,
) -> dict[str, Any]:
    existing: ImapCursor | None = await state.cursors.lookup(account_id)
    if existing and existing.uid_validity == str(uid_validity):
        return {"kind": "resume", "cursor": existing}

    cursor = ImapCursor(
        uid_validity=str(uid_validity),
        last_seen_uid=max(0, uid_next - 1),
        updated_at=time.time(),
    )
    await state.cursors.register(account_id, cursor)
    kind: Literal["reset", "baseline"] = "reset" if existing else "baseline"
    return {"kind": kind, "cursor": cursor}


async def advance_imap_cursor(
    state: ImapWatcherState,
    account_id: str,
    uid_validity: str,
    uid: int,
) -> None:
    await state.cursors.register(
        account_id,
        ImapCursor(
            uid_validity=str(uid_validity),
            last_seen_uid=uid,
            updated_at=time.time(),
        ),
    )


async def remember_imap_message(
    state: ImapWatcherState,
    account_id: str,
    message_id: str,
) -> bool:
    ring: ImapMessageRing | None = await state.message_ids.lookup(account_id)
    existing_ids = ring.message_ids if ring else []
    if message_id in existing_ids:
        return False
    updated_ids = (existing_ids + [message_id])[-100:]
    await state.message_ids.register(
        account_id,
        ImapMessageRing(message_ids=updated_ids),
    )
    return True


async def count_imap_skip(
    state: ImapWatcherState,
    account_id: str,
    reason: str,
) -> None:
    key = f"{account_id}:{reason}"
    current = await state.skips.lookup(key)
    count = (
        current.get("count", 0)
        if isinstance(current, dict)
        else getattr(current, "count", 0)
        if current
        else 0
    )
    await state.skips.register(key, {"count": min(count + 1, 1_000_000)})


async def record_imap_attempt(
    state: ImapWatcherState,
    message_key: str,
    reason: str,
) -> int:
    key = f"attempt:{message_key}"
    previous = await state.claims.lookup(key)
    count = 0
    if isinstance(previous, ImapAttempt):
        count = previous.count
    elif isinstance(previous, dict):
        count = previous.get("count", 0)
    new_count = count + 1
    await state.claims.register(key, ImapAttempt(count=new_count, reason=reason))
    return new_count
