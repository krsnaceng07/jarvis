"""source_sync_state — Memory Wiki source-sync state.

OpenClaw parity: mirrors
``extensions/memory-wiki/src/source-sync-state.ts``.

Tracks per-vault import metadata for the
memory-wiki plugin's "imported source" pages
(``bridge`` group + ``unsafe-local`` group).
The state store is keyed by the SHA-256 of the
vault's realpath; each entry records the
``pagePath`` + ``sourcePath`` + a
``renderFingerprint`` so a later compile pass
can detect "source file unchanged; skip the
import write".

Phase 4.3e-mr1 ships the in-memory + keyed-store
implementations. The full SQLite-backed
plugin-blob-store variant (used by
``compiled-cache`` in 4.3e-mr3) lands in
Phase 4.3e-mr3.
"""

from __future__ import annotations

import contextlib
import hashlib
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypeVar

from jarvis_sdk import (
    OpenKeyedStoreOptionsAsync as OpenKeyedStoreOptions,
    PluginStateKeyedStore,
    open_plugin_state_keyed_store,
    read_json_file_with_fallback,
)

_T = TypeVar("_T")


# Mirrors the OpenClaw
# ``MEMORY_WIKI_SOURCE_SYNC_STATE_NAMESPACE``
# + ``MEMORY_WIKI_SOURCE_SYNC_STATE_MAX_ENTRIES``
# constants. The namespace string is shared
# with the SQLite-backed plugin-blob-store
# variant so the two stores can co-exist.
MEMORY_WIKI_SOURCE_SYNC_STATE_NAMESPACE = "source-sync"
MEMORY_WIKI_SOURCE_SYNC_STATE_MAX_ENTRIES = 20_000


# The set of valid ``group`` values. The
# OpenClaw source uses a string-literal type;
# the Python port mirrors the shape with a
# runtime ``frozenset`` (the data model is
# identical, but Python doesn't have string
# literal types).
VALID_SOURCE_SYNC_GROUPS: frozenset[str] = frozenset({"bridge", "unsafe-local"})


@dataclass(frozen=True, slots=True)
class MemoryWikiImportedSourceGroup:
    """The source-sync group identifier.

    The OpenClaw source uses a string-literal
    type (``"bridge" | "unsafe-local"``); the
    Python port keeps a class-style wrapper so
    callers can pass either a string or a
    ``MemoryWikiImportedSourceGroup`` instance.
    """

    value: str

    def __post_init__(self) -> None:
        if self.value not in VALID_SOURCE_SYNC_GROUPS:
            raise ValueError(
                f"Invalid source-sync group {self.value!r}; "
                f"expected one of {sorted(VALID_SOURCE_SYNC_GROUPS)}"
            )

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class MemoryWikiImportedSourceStateEntry:
    """A single source-sync entry. Mirrors ``MemoryWikiImportedSourceStateEntry``."""

    group: str
    page_path: str
    source_path: str
    source_updated_at_ms: int
    source_size: int
    render_fingerprint: str


@dataclass(frozen=True, slots=True)
class MemoryWikiImportedSourceState:
    """The state stored on disk under ``.openclaw-wiki/source-sync.json``.

    Mirrors ``MemoryWikiImportedSourceState``.
    The ``version`` is fixed to ``1`` (the
    OpenClaw schema version); the ``entries``
    dict is keyed by ``syncKey`` (a stable
    identity derived from the source file).
    """

    version: int = 1
    entries: dict[str, MemoryWikiImportedSourceStateEntry] = field(default_factory=dict)


def _normalize_state(value: Any) -> MemoryWikiImportedSourceState:
    """Parse a raw JSON value into a ``MemoryWikiImportedSourceState``.

    Mirrors OpenClaw's
    ``normalizeSourceSyncState``. Returns the
    empty state if ``value`` is not a valid
    source-sync state (so the caller doesn't
    have to handle ``None`` separately).
    """
    empty = MemoryWikiImportedSourceState()
    if not isinstance(value, dict):
        return empty
    if value.get("version") != 1:
        return empty
    raw_entries = value.get("entries")
    if not isinstance(raw_entries, dict):
        return empty
    entries: dict[str, MemoryWikiImportedSourceStateEntry] = {}
    for sync_key, raw_entry in raw_entries.items():
        if not isinstance(sync_key, str) or not sync_key:
            continue
        if not isinstance(raw_entry, dict):
            continue
        group: Any = raw_entry.get("group")
        if group not in VALID_SOURCE_SYNC_GROUPS:
            continue
        page_path: Any = raw_entry.get("pagePath")
        source_path: Any = raw_entry.get("sourcePath")
        source_updated_at_ms: Any = raw_entry.get("sourceUpdatedAtMs")
        source_size: Any = raw_entry.get("sourceSize")
        render_fingerprint: Any = raw_entry.get("renderFingerprint")
        if (
            not isinstance(page_path, str)
            or not isinstance(source_path, str)
            or not isinstance(source_updated_at_ms, int)
            or not isinstance(source_size, int)
            or not isinstance(render_fingerprint, str)
        ):
            continue
        entries[sync_key] = MemoryWikiImportedSourceStateEntry(
            group=group,
            page_path=page_path,
            source_path=source_path,
            source_updated_at_ms=source_updated_at_ms,
            source_size=source_size,
            render_fingerprint=render_fingerprint,
        )
    return MemoryWikiImportedSourceState(version=1, entries=entries)


def _resolve_vault_root_key(vault_root: str) -> str:
    """Compute the SHA-256-derived vault key.

    Mirrors OpenClaw's ``resolveVaultRootKey``:
    SHA-256 of the absolute vault path, sliced
    to 32 hex chars. The same key is used by
    the SQLite-backed ``compiled-cache`` so
    the keyed-store namespace is shared.
    """
    absolute = os.path.abspath(vault_root)
    return hashlib.sha256(absolute.encode("utf-8")).hexdigest()[:32]


def _resolve_state_entry_key(vault_root_key: str, sync_key: str) -> str:
    """SHA-256-derived per-entry key.

    Mirrors OpenClaw's
    ``resolveStateEntryKey``. Includes the
    vault root key so different vaults can't
    collide.
    """
    payload = f"{vault_root_key}\0{sync_key}".encode()
    return hashlib.sha256(payload).hexdigest()


def resolve_memory_wiki_source_sync_state_path(vault_root: str) -> str:
    """Return the on-disk path of the legacy source-sync state.

    Mirrors OpenClaw's
    ``resolveMemoryWikiSourceSyncStatePath``.
    The legacy file is read on init (and
    migrated into the keyed store) but the
    keyed store is the canonical persistence
    layer from 4.3e-mr1 onward.
    """
    return os.path.join(vault_root, ".openclaw-wiki", "source-sync.json")


class MemoryWikiSourceSyncStateStore:
    """The store API exposed to callers.

    Mirrors the OpenClaw
    ``MemoryWikiSourceSyncStateStore`` shape.
    The actual persistence is delegated to
    the underlying
    :class:`PluginStateKeyedStore`.
    """

    def __init__(self, store: PluginStateKeyedStore[dict[str, Any]]) -> None:
        self._store = store

    def read(self, vault_root: str) -> MemoryWikiImportedSourceState:
        """Read the source-sync state for ``vault_root``.

        Mirrors OpenClaw's ``store.read``.
        Iterates every entry in the keyed store
        and keeps only those whose
        ``vaultRootKey`` matches the input
        vault. Returns the empty state if no
        entries match.
        """
        vault_root_key = _resolve_vault_root_key(vault_root)
        entries: dict[str, MemoryWikiImportedSourceStateEntry] = {}
        for entry in self._store.entries():
            value = _read_entry_value(entry)
            if not isinstance(value, dict):
                continue
            if value.get("vaultRootKey") != vault_root_key:
                continue
            sync_key = value.get("syncKey")
            if not isinstance(sync_key, str):
                continue
            # Re-parse the entry via
            # ``_normalize_state`` so a corrupt
            # row doesn't poison the rest of the
            # state.
            normalized = _normalize_state(
                {
                    "version": 1,
                    "entries": {sync_key: value},
                }
            )
            entry_obj = normalized.entries.get(sync_key)
            if entry_obj is not None:
                entries[sync_key] = entry_obj
        return MemoryWikiImportedSourceState(version=1, entries=entries)

    def write(
        self,
        vault_root: str,
        state: MemoryWikiImportedSourceState,
        plan: MemoryWikiSourceSyncStateWritePlan | None = None,
    ) -> None:
        """Write ``state`` to the keyed store.

        Mirrors OpenClaw's ``store.write``. When
        ``plan`` is provided, the writer applies
        only the keys it lists (an upsert
        for every ``upsert_key`` + a delete for
        every ``delete_key``). When ``plan`` is
        ``None``, the writer syncs the whole
        state: upserts every entry and deletes
        any stale keys that belong to this vault
        but are no longer in ``state``.
        """
        _assert_within_capacity(state)
        vault_root_key = _resolve_vault_root_key(vault_root)
        if plan is not None:
            for sync_key in plan.delete_keys:
                self._store.delete(_resolve_state_entry_key(vault_root_key, sync_key))
            for sync_key in plan.upsert_keys:
                entry = state.entries.get(sync_key)
                if entry is None:
                    raise ValueError(f"Missing tracked Memory Wiki source sync entry: {sync_key!r}")
                self._store.register(
                    _resolve_state_entry_key(vault_root_key, sync_key),
                    _entry_to_record(vault_root_key, sync_key, entry),
                )
            return
        # Full-sync path: drop every existing
        # entry that belongs to this vault but
        # isn't in the new state, then upsert
        # the new entries. To match OpenClaw's
        # "skip unchanged rows" optimization, the
        # writer only calls ``register`` when the
        # new entry actually differs from the
        # existing one.
        next_keys = {
            _resolve_state_entry_key(vault_root_key, sync_key) for sync_key in state.entries
        }
        existing_by_key: dict[str, dict[str, Any]] = {}
        for row in self._store.entries():
            value = _read_entry_value(row)
            if not isinstance(value, dict):
                continue
            if value.get("vaultRootKey") != vault_root_key:
                continue
            existing_by_key[_read_entry_key(row)] = value
        for stored_key, _stored_value in existing_by_key.items():
            if stored_key not in next_keys:
                self._store.delete(stored_key)
        for sync_key, entry in state.entries.items():
            store_key = _resolve_state_entry_key(vault_root_key, sync_key)
            new_record = _entry_to_record(vault_root_key, sync_key, entry)
            existing = existing_by_key.get(store_key)
            if existing is not None and _records_equal(existing, new_record):
                continue
            self._store.register(store_key, new_record)


def _entry_to_record(
    vault_root_key: str,
    sync_key: str,
    entry: MemoryWikiImportedSourceStateEntry,
) -> dict[str, Any]:
    """Serialize a source-sync entry to a JSON-friendly dict."""
    return {
        "vaultRootKey": vault_root_key,
        "syncKey": sync_key,
        "group": entry.group,
        "pagePath": entry.page_path,
        "sourcePath": entry.source_path,
        "sourceUpdatedAtMs": entry.source_updated_at_ms,
        "sourceSize": entry.source_size,
        "renderFingerprint": entry.render_fingerprint,
    }


def _read_entry_value(entry: Any) -> Any:
    """Read the ``value`` field from a store entry.

    The :class:`PluginStateKeyedStore.entries`
    method returns a list of
    :class:`PluginStateEntry` (with a ``.value``
    attribute) under normal use, but the
    OpenClaw async API returns a list of dicts
    (with a ``.key`` + ``["value"]`` shape). The
    Python port accepts both for parity with
    the OpenClaw test helpers.
    """
    if isinstance(entry, dict):
        return entry.get("value")
    return getattr(entry, "value", None)


def _read_entry_key(entry: Any) -> str:
    """Read the ``key`` field from a store entry.

    Mirrors :func:`_read_entry_value`; returns
    the ``key`` field for both the dict shape
    and the dataclass shape.
    """
    if isinstance(entry, dict):
        raw = entry.get("key")
        if isinstance(raw, str):
            return raw
        return ""
    raw = getattr(entry, "key", None)
    return raw if isinstance(raw, str) else ""


def _records_equal(left: dict[str, Any], right: dict[str, Any]) -> bool:
    """Return True iff two source-sync records are equivalent.

    Used by the full-sync writer to skip
    ``register`` calls when the new record is
    byte-for-byte equivalent to the existing
    one (so the OpenClaw "persists only
    changed rows" optimization is preserved).
    """
    # Compare the user-facing fields only;
    # ``vaultRootKey`` + ``syncKey`` are
    # deterministically derived from the
    # ``sync_key`` argument.
    for key in (
        "group",
        "pagePath",
        "sourcePath",
        "sourceUpdatedAtMs",
        "sourceSize",
        "renderFingerprint",
    ):
        if left.get(key) != right.get(key):
            return False
    return True


def _assert_within_capacity(state: MemoryWikiImportedSourceState) -> None:
    """Raise if the state exceeds the keyed-store entry cap.

    Mirrors OpenClaw's
    ``assertSourceSyncStateWithinLimit``. The
    Python port enforces the cap here (the
    keyed store enforces it again on insert,
    but the in-memory store accepts the insert
    and silently evicts — pre-checking keeps
    the behavior consistent with the
    SQLite-backed OpenClaw variant).
    """
    count = len(state.entries)
    if count > MEMORY_WIKI_SOURCE_SYNC_STATE_MAX_ENTRIES:
        raise MemoryWikiSourceSyncCapacityError(
            f"Memory Wiki source sync state exceeds SQLite entry limit "
            f"({count}/{MEMORY_WIKI_SOURCE_SYNC_STATE_MAX_ENTRIES})"
        )


class MemoryWikiSourceSyncCapacityError(RuntimeError):
    """Raised when a source-sync write would exceed the entry cap."""


def assert_memory_wiki_source_sync_state_capacity(
    *,
    state: MemoryWikiImportedSourceState,
    group: str,
    incoming_count: int,
) -> None:
    """Pre-flight capacity check for an incoming source-sync group.

    Mirrors OpenClaw's
    ``assertMemoryWikiSourceSyncStateCapacity``.
    Counts the retained entries from other
    groups + the projected incoming count and
    raises if the total exceeds the cap.
    """
    if group not in VALID_SOURCE_SYNC_GROUPS:
        raise ValueError(f"Invalid source-sync group {group!r}")
    retained_other = sum(1 for entry in state.entries.values() if entry.group != group)
    projected = retained_other + incoming_count
    if projected > MEMORY_WIKI_SOURCE_SYNC_STATE_MAX_ENTRIES:
        raise MemoryWikiSourceSyncCapacityError(
            f"Memory Wiki source sync state exceeds SQLite entry limit "
            f"({projected}/{MEMORY_WIKI_SOURCE_SYNC_STATE_MAX_ENTRIES})"
        )


# Module-level configured store.
# Mirrors OpenClaw's
# ``configuredSourceSyncStore``. The Python
# port defaults to ``None`` so the public
# ``read`` / ``write`` helpers fall back to
# the in-memory keyed store.
_configured_source_sync_store: MemoryWikiSourceSyncStateStore | None = None
_memory_fallback_state_by_vault: dict[str, MemoryWikiImportedSourceState] = {}


def create_memory_wiki_source_sync_state_store(
    open_keyed_store: Any | None = None,
) -> MemoryWikiSourceSyncStateStore:
    """Build a store bound to a keyed-store namespace.

    Mirrors OpenClaw's
    ``createMemoryWikiSourceSyncStateStore``.
    ``open_keyed_store`` is the OpenClaw
    ``openKeyedStore`` factory; the Python port
    uses the default in-memory fallback when
    it's ``None`` (matching the OpenClaw
    ``createMemoryFallbackStateStore``
    behavior).
    """
    if open_keyed_store is None:
        async_store = _default_keyed_store_factory()
    else:
        async_store = open_keyed_store(
            OpenKeyedStoreOptions(
                namespace=MEMORY_WIKI_SOURCE_SYNC_STATE_NAMESPACE,
                max_entries=MEMORY_WIKI_SOURCE_SYNC_STATE_MAX_ENTRIES,
                overflow_policy="reject-new",
            )
        )
    return MemoryWikiSourceSyncStateStore(async_store)


def _default_keyed_store_factory() -> PluginStateKeyedStore[dict[str, Any]]:
    """Build a default in-memory keyed store for the source-sync namespace."""
    return open_plugin_state_keyed_store(
        OpenKeyedStoreOptions(
            namespace=MEMORY_WIKI_SOURCE_SYNC_STATE_NAMESPACE,
            max_entries=MEMORY_WIKI_SOURCE_SYNC_STATE_MAX_ENTRIES,
            overflow_policy="reject-new",
        )
    )


def create_memory_fallback_state_store() -> MemoryWikiSourceSyncStateStore:
    """Return the in-memory fallback store.

    Mirrors OpenClaw's
    ``createMemoryFallbackStateStore``. Used
    by tests and by the public
    ``read`` / ``write`` helpers when no store
    is configured.
    """
    return create_memory_wiki_source_sync_state_store()


def configure_memory_wiki_source_sync_state_store(
    store: MemoryWikiSourceSyncStateStore | None,
) -> None:
    """Configure the process-wide source-sync store.

    Mirrors OpenClaw's
    ``configureMemoryWikiSourceSyncStateStore``.
    ``None`` resets to the in-memory fallback.
    """
    global _configured_source_sync_store  # noqa: PLW0603 — process-wide SDK config
    _configured_source_sync_store = store


def _resolve_source_sync_store(
    store: MemoryWikiSourceSyncStateStore | None = None,
) -> MemoryWikiSourceSyncStateStore:
    """Pick the configured store, or fall back to the in-memory default."""
    if store is not None:
        return store
    if _configured_source_sync_store is not None:
        return _configured_source_sync_store
    return create_memory_fallback_state_store()


def read_memory_wiki_source_sync_state(
    vault_root: str,
    store: MemoryWikiSourceSyncStateStore | None = None,
) -> MemoryWikiImportedSourceState:
    """Read the source-sync state for ``vault_root``.

    Mirrors OpenClaw's
    ``readMemoryWikiSourceSyncState``.
    """
    return _resolve_source_sync_store(store).read(vault_root)


def read_legacy_memory_wiki_source_sync_state(
    vault_root: str,
) -> MemoryWikiImportedSourceState:
    """Read the legacy on-disk source-sync state.

    Mirrors OpenClaw's
    ``readLegacyMemoryWikiSourceSyncState``.
    The legacy file lives at
    ``.openclaw-wiki/source-sync.json``; this
    helper is used by the bootstrap / migration
    path to load the v0 format.
    """
    state_path = resolve_memory_wiki_source_sync_state_path(vault_root)
    result = read_json_file_with_fallback(state_path, {"version": 1, "entries": {}})
    return _normalize_state(result["value"])


def write_memory_wiki_source_sync_state(
    vault_root: str,
    state: MemoryWikiImportedSourceState,
    store: MemoryWikiSourceSyncStateStore | None = None,
    *,
    plan: MemoryWikiSourceSyncStateWritePlan | None = None,
) -> None:
    """Write the source-sync state to the keyed store.

    Mirrors OpenClaw's
    ``writeMemoryWikiSourceSyncState``. When
    ``plan`` is provided, the writer applies
    only the listed upsert / delete keys; the
    rest of the state is left untouched.
    """
    _resolve_source_sync_store(store).write(vault_root, state, plan=plan)


def should_skip_imported_source_write(
    *,
    vault_root: str,
    sync_key: str,
    expected_page_path: str,
    expected_source_path: str,
    source_updated_at_ms: int,
    source_size: int,
    render_fingerprint: str,
    state: MemoryWikiImportedSourceState,
) -> bool:
    """Return True iff the cached entry matches and the page is on disk.

    Mirrors OpenClaw's
    ``shouldSkipImportedSourceWrite``. Skips
    the import write when the source file is
    unchanged (matching size + mtime-ms +
    render fingerprint) AND the page file
    still exists on disk.
    """
    entry = state.entries.get(sync_key)
    if entry is None:
        return False
    if (
        entry.page_path != expected_page_path
        or entry.source_path != expected_source_path
        or entry.source_updated_at_ms != source_updated_at_ms
        or entry.source_size != source_size
        or entry.render_fingerprint != render_fingerprint
    ):
        return False
    page_abs = os.path.join(vault_root, expected_page_path)
    return os.path.exists(page_abs)


def set_imported_source_entry(
    *,
    sync_key: str,
    entry: MemoryWikiImportedSourceStateEntry,
    state: MemoryWikiImportedSourceState,
) -> None:
    """Upsert ``entry`` into ``state`` (no-op if unchanged).

    Mirrors OpenClaw's
    ``setImportedSourceEntry``. Skips the
    write when every field of the new entry
    matches the existing one.
    """
    current = state.entries.get(sync_key)
    if (
        current is not None
        and current.group == entry.group
        and current.page_path == entry.page_path
        and current.source_path == entry.source_path
        and current.source_updated_at_ms == entry.source_updated_at_ms
        and current.source_size == entry.source_size
        and current.render_fingerprint == entry.render_fingerprint
    ):
        return
    state.entries[sync_key] = entry


def is_source_within_configured_path(source_path: str, configured_path: str) -> bool:
    """Return True iff ``source_path`` is within ``configured_path``.

    Mirrors OpenClaw's ``isSourceWithinConfiguredPath`` helper. The
    unsafe-local import path uses this to decide which prior
    source-sync entries to retain when a configured source scope
    is no longer readable (so the human notes on those pages are
    preserved until the scope is mounted again or removed from
    config). The check is "is the relative path from
    ``configured_path`` to ``source_path`` neither ascending
    nor absolute?" — so the source must live strictly under the
    configured root.
    """
    try:
        relative = os.path.relpath(source_path, configured_path)
    except (OSError, ValueError):
        return False
    if relative == ".":
        return True
    if relative == "..":
        return False
    if relative.startswith(f"..{os.sep}"):
        return False
    return not os.path.isabs(relative)


def prune_imported_source_entries(
    *,
    vault_root: str,
    group: str,
    active_keys: set[str],
    state: MemoryWikiImportedSourceState,
) -> int:
    """Remove entries for ``group`` whose keys are not in ``active_keys``.

    Mirrors OpenClaw's
    ``pruneImportedSourceEntries``. Best-effort
    removes the page file from disk and
    deletes the entry from ``state``.
    Returns the number of removed entries.
    """
    if group not in VALID_SOURCE_SYNC_GROUPS:
        raise ValueError(f"Invalid source-sync group {group!r}")
    removed = 0
    for sync_key in list(state.entries):
        entry = state.entries[sync_key]
        if entry.group != group or sync_key in active_keys:
            continue
        page_abs = os.path.join(vault_root, entry.page_path)
        with contextlib.suppress(OSError):
            Path(page_abs).unlink(missing_ok=True)
        del state.entries[sync_key]
        removed += 1
    return removed


@dataclass(frozen=True, slots=True)
class MemoryWikiSourceSyncStateWritePlan:
    """The optional plan passed to ``write`` for partial updates.

    Mirrors OpenClaw's
    ``MemoryWikiSourceSyncStateWritePlan``.
    """

    upsert_keys: list[str] = field(default_factory=list)
    delete_keys: list[str] = field(default_factory=list)


def reset_memory_wiki_source_sync_state_for_tests() -> None:
    """Reset module-level state (test-only helper).

    Clears the configured store + the
    in-memory fallback so subsequent tests
    start from a clean slate. Production code
    MUST NOT call this.
    """
    global _configured_source_sync_store, _memory_fallback_state_by_vault  # noqa: PLW0603 — test-only state
    _configured_source_sync_store = None
    _memory_fallback_state_by_vault = {}


__all__ = [
    "MEMORY_WIKI_SOURCE_SYNC_STATE_MAX_ENTRIES",
    "MEMORY_WIKI_SOURCE_SYNC_STATE_NAMESPACE",
    "VALID_SOURCE_SYNC_GROUPS",
    "MemoryWikiImportedSourceGroup",
    "MemoryWikiImportedSourceState",
    "MemoryWikiImportedSourceStateEntry",
    "MemoryWikiSourceSyncCapacityError",
    "MemoryWikiSourceSyncStateStore",
    "MemoryWikiSourceSyncStateWritePlan",
    "assert_memory_wiki_source_sync_state_capacity",
    "configure_memory_wiki_source_sync_state_store",
    "create_memory_fallback_state_store",
    "create_memory_wiki_source_sync_state_store",
    "is_source_within_configured_path",
    "prune_imported_source_entries",
    "read_legacy_memory_wiki_source_sync_state",
    "read_memory_wiki_source_sync_state",
    "resolve_memory_wiki_source_sync_state_path",
    "reset_memory_wiki_source_sync_state_for_tests",
    "set_imported_source_entry",
    "should_skip_imported_source_write",
    "write_memory_wiki_source_sync_state",
]
