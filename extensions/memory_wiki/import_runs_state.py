"""import_runs_state — Memory Wiki import-run state.

OpenClaw parity: mirrors
``extensions/memory-wiki/src/import-runs-state.ts``.

Tracks per-vault import-run metadata for the
memory-wiki plugin's chatgpt-import pipeline.
The state store is keyed by the SHA-256 of the
vault's realpath; each import run is split
into a ``meta`` row (everything but the path
lists) + one ``created-path`` /
``updated-path`` row per affected page.

Phase 4.3e-mr2 ships the in-memory + keyed-store
implementations. The full SQLite-backed
plugin-blob-store variant lands in Phase
4.3e-mr3 (compiled-cache).

Legacy path
-----------
The OpenClaw plugin also reads a legacy
``{vault}/.openclaw-wiki/import-runs/*.json``
directory format; the Python port mirrors this
with
:func:`read_legacy_memory_wiki_import_run_records`.
The doctor migration in Phase 4.3g uses this
to bootstrap the keyed store.
"""

from __future__ import annotations

import hashlib
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from jarvis_sdk import (
    OpenKeyedStoreOptionsAsync as OpenKeyedStoreOptions,
    PluginStateKeyedStore,
    open_plugin_state_keyed_store,
)

# Mirrors the OpenClaw
# ``MEMORY_WIKI_IMPORT_RUN_STATE_NAMESPACE`` +
# ``MEMORY_WIKI_IMPORT_RUN_STATE_MAX_ENTRIES``
# constants. The keyed store rejects new
# inserts past the cap.
MEMORY_WIKI_IMPORT_RUN_STATE_NAMESPACE = "import-runs"
MEMORY_WIKI_IMPORT_RUN_STATE_MAX_ENTRIES = 20_000

# Concurrency cap for the legacy directory
# read. Mirrors the OpenClaw
# ``LEGACY_IMPORT_RUN_READ_CONCURRENCY = 16``
# constant.
LEGACY_IMPORT_RUN_READ_CONCURRENCY = 16


# Supported ``importType`` values. The OpenClaw
# source only ships ``"chatgpt"`` but the
# record type is extensible.
SUPPORTED_IMPORT_TYPES: frozenset[str] = frozenset({"chatgpt"})


@dataclass(frozen=True, slots=True)
class ChatGptImportRunEntry:
    """One updated-path row. Mirrors the OpenClaw ``ChatGptImportRunEntry`` shape."""

    path: str
    snapshot_path: str | None = None


@dataclass(frozen=True, slots=True)
class ChatGptImportRunRecord:
    """One ChatGPT import run. Mirrors the OpenClaw ``ChatGptImportRunRecord`` shape."""

    run_id: str
    import_type: str
    export_path: str
    source_path: str
    applied_at: str
    conversation_count: int
    created_count: int
    updated_count: int
    skipped_count: int
    created_paths: list[str] = field(default_factory=list)
    updated_paths: list[ChatGptImportRunEntry] = field(default_factory=list)
    rolled_back_at: str | None = None


# ── private row types ─────────────────────────────────────


@dataclass(frozen=True, slots=True)
class MemoryWikiImportRunMetaStateRecord:
    """The meta row for an import run. Mirrors the OpenClaw ``MemoryWikiImportRunMetaStateRecord`` shape."""

    vault_root_key: str
    run_id: str
    import_type: str
    export_path: str
    source_path: str
    applied_at: str
    conversation_count: int
    created_count: int
    updated_count: int
    skipped_count: int
    rolled_back_at: str | None = None


@dataclass(frozen=True, slots=True)
class MemoryWikiImportRunPathStateRecord:
    """A single path row. Mirrors the OpenClaw ``MemoryWikiImportRunPathStateRecord`` shape."""

    vault_root_key: str
    run_id: str
    index: int
    path: str
    kind: str  # "created-path" | "updated-path"
    snapshot_path: str | None = None


# ── keyed-store row type ──────────────────────────────────


StateRecord = MemoryWikiImportRunMetaStateRecord | MemoryWikiImportRunPathStateRecord


# ── internal helpers ──────────────────────────────────────


def _as_dict(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    return value


def _as_string_array(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [entry for entry in value if isinstance(entry, str) and entry.strip()]


def _as_non_negative_integer(value: Any) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        return 0
    if value < 0:
        return 0
    return int(value)


def _as_optional_trimmed_string(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    trimmed = value.strip()
    return trimmed or None


def _resolve_vault_root_key(vault_root: str) -> str:
    """SHA-256 of the absolute vault path, sliced to 32 hex chars.

    Mirrors the OpenClaw ``resolveVaultRootKey``.
    """
    absolute = os.path.abspath(vault_root)
    return hashlib.sha256(absolute.encode("utf-8")).hexdigest()[:32]


def _resolve_state_entry_key(vault_root_key: str, run_id: str) -> str:
    """SHA-256 of ``vault_root_key + 0 + "meta" + 0 + run_id``.

    Mirrors the OpenClaw
    ``resolveStateEntryKey``. The
    ``\\0`` separators prevent
    ``runId="a"/vault="b"`` and
    ``runId="a"/vault="ba"`` from colliding.
    """
    payload = f"{vault_root_key}\0meta\0{run_id}".encode()
    return hashlib.sha256(payload).hexdigest()


def _resolve_path_state_entry_key(
    *,
    vault_root_key: str,
    run_id: str,
    kind: str,
    index: int,
    path: str,
) -> str:
    """SHA-256 of the path-row identity. Mirrors the OpenClaw helper."""
    payload = f"{vault_root_key}\0{run_id}\0{kind}\0{index}\0{path}".encode()
    return hashlib.sha256(payload).hexdigest()


def _as_record_kind(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    if value in ("created-path", "updated-path"):
        return value
    return None


def _normalize_run_record(raw: Any) -> ChatGptImportRunRecord | None:
    """Normalize a raw record into a :class:`ChatGptImportRunRecord`.

    Mirrors OpenClaw's
    ``normalizeMemoryWikiImportRunRecord``. The
    function is strict: any required field
    missing / wrong type returns ``None`` so
    corrupt rows are dropped (rather than
    poisoning the rest of the state).
    """
    record = _as_dict(raw)
    if record is None:
        return None
    if record.get("version") != 1:
        return None
    if record.get("importType") not in SUPPORTED_IMPORT_TYPES:
        return None
    run_id = _as_optional_trimmed_string(record.get("runId"))
    export_path = _as_optional_trimmed_string(record.get("exportPath"))
    source_path = _as_optional_trimmed_string(record.get("sourcePath"))
    applied_at = _as_optional_trimmed_string(record.get("appliedAt"))
    if not (run_id and export_path and source_path and applied_at):
        return None
    raw_updated_paths = record.get("updatedPaths")
    updated_paths: list[ChatGptImportRunEntry] = []
    if isinstance(raw_updated_paths, list):
        for entry in raw_updated_paths:
            entry_dict = _as_dict(entry)
            if entry_dict is None:
                continue
            entry_path = _as_optional_trimmed_string(entry_dict.get("path"))
            if not entry_path:
                continue
            snapshot_path = _as_optional_trimmed_string(entry_dict.get("snapshotPath"))
            if snapshot_path is None:
                updated_paths.append(ChatGptImportRunEntry(path=entry_path))
            else:
                updated_paths.append(
                    ChatGptImportRunEntry(path=entry_path, snapshot_path=snapshot_path)
                )
    return ChatGptImportRunRecord(
        run_id=run_id,
        import_type=record["importType"],
        export_path=export_path,
        source_path=source_path,
        applied_at=applied_at,
        conversation_count=_as_non_negative_integer(record.get("conversationCount")),
        created_count=_as_non_negative_integer(record.get("createdCount")),
        updated_count=_as_non_negative_integer(record.get("updatedCount")),
        skipped_count=_as_non_negative_integer(record.get("skippedCount")),
        created_paths=_as_string_array(record.get("createdPaths")),
        updated_paths=updated_paths,
        rolled_back_at=_as_optional_trimmed_string(record.get("rolledBackAt")),
    )


def _normalize_meta_record(
    raw: Any,
) -> MemoryWikiImportRunMetaStateRecord | None:
    """Parse a meta row out of a raw dict."""
    record = _as_dict(raw)
    if record is None or record.get("kind") != "meta":
        return None
    vault_root_key = _as_optional_trimmed_string(record.get("vaultRootKey"))
    if not vault_root_key:
        return None
    run_record = _normalize_run_record(
        {
            **record,
            "createdPaths": [],
            "updatedPaths": [],
        }
    )
    if run_record is None:
        return None
    return MemoryWikiImportRunMetaStateRecord(
        vault_root_key=vault_root_key,
        run_id=run_record.run_id,
        import_type=run_record.import_type,
        export_path=run_record.export_path,
        source_path=run_record.source_path,
        applied_at=run_record.applied_at,
        conversation_count=run_record.conversation_count,
        created_count=run_record.created_count,
        updated_count=run_record.updated_count,
        skipped_count=run_record.skipped_count,
        rolled_back_at=run_record.rolled_back_at,
    )


def _normalize_path_record(
    raw: Any,
) -> MemoryWikiImportRunPathStateRecord | None:
    """Parse a path row out of a raw dict."""
    record = _as_dict(raw)
    if record is None:
        return None
    kind = _as_record_kind(record.get("kind"))
    if kind is None:
        return None
    vault_root_key = _as_optional_trimmed_string(record.get("vaultRootKey"))
    run_id = _as_optional_trimmed_string(record.get("runId"))
    path = _as_optional_trimmed_string(record.get("path"))
    index_raw = record.get("index")
    if not (
        vault_root_key
        and run_id
        and path
        and isinstance(index_raw, int)
        and not isinstance(index_raw, bool)
    ):
        return None
    snapshot_path = _as_optional_trimmed_string(record.get("snapshotPath"))
    return MemoryWikiImportRunPathStateRecord(
        vault_root_key=vault_root_key,
        run_id=run_id,
        index=max(0, int(index_raw)),
        path=path,
        kind=kind,
        snapshot_path=snapshot_path,
    )


def _clone_run_record(record: ChatGptImportRunRecord) -> ChatGptImportRunRecord:
    """Return a defensive deep copy of ``record``."""
    return ChatGptImportRunRecord(
        run_id=record.run_id,
        import_type=record.import_type,
        export_path=record.export_path,
        source_path=record.source_path,
        applied_at=record.applied_at,
        conversation_count=record.conversation_count,
        created_count=record.created_count,
        updated_count=record.updated_count,
        skipped_count=record.skipped_count,
        created_paths=list(record.created_paths),
        updated_paths=[
            ChatGptImportRunEntry(
                path=entry.path,
                snapshot_path=entry.snapshot_path,
            )
            for entry in record.updated_paths
        ],
        rolled_back_at=record.rolled_back_at,
    )


def _compose_run_record(
    meta: MemoryWikiImportRunMetaStateRecord,
    path_rows: list[MemoryWikiImportRunPathStateRecord],
) -> ChatGptImportRunRecord:
    """Stitch a meta row + path rows into a :class:`ChatGptImportRunRecord`.

    Mirrors the OpenClaw
    ``composeImportRunRecord``. Created paths
    come first (sorted by ``index``), then
    updated paths.
    """
    created_paths = sorted(
        (row for row in path_rows if row.kind == "created-path"),
        key=lambda row: row.index,
    )
    updated_paths = sorted(
        (row for row in path_rows if row.kind == "updated-path"),
        key=lambda row: row.index,
    )
    return ChatGptImportRunRecord(
        run_id=meta.run_id,
        import_type=meta.import_type,
        export_path=meta.export_path,
        source_path=meta.source_path,
        applied_at=meta.applied_at,
        conversation_count=meta.conversation_count,
        created_count=meta.created_count,
        updated_count=meta.updated_count,
        skipped_count=meta.skipped_count,
        created_paths=[row.path for row in created_paths],
        updated_paths=[
            ChatGptImportRunEntry(
                path=row.path,
                snapshot_path=row.snapshot_path,
            )
            for row in updated_paths
        ],
        rolled_back_at=meta.rolled_back_at,
    )


def _to_meta_record(
    vault_root_key: str,
    record: ChatGptImportRunRecord,
) -> MemoryWikiImportRunMetaStateRecord:
    """Build the meta row from a :class:`ChatGptImportRunRecord`."""
    return MemoryWikiImportRunMetaStateRecord(
        vault_root_key=vault_root_key,
        run_id=record.run_id,
        import_type=record.import_type,
        export_path=record.export_path,
        source_path=record.source_path,
        applied_at=record.applied_at,
        conversation_count=record.conversation_count,
        created_count=record.created_count,
        updated_count=record.updated_count,
        skipped_count=record.skipped_count,
        rolled_back_at=record.rolled_back_at,
    )


def _to_path_records(
    vault_root_key: str,
    record: ChatGptImportRunRecord,
) -> list[MemoryWikiImportRunPathStateRecord]:
    """Build the path rows from a :class:`ChatGptImportRunRecord`."""
    rows: list[MemoryWikiImportRunPathStateRecord] = []
    for index, path in enumerate(record.created_paths):
        rows.append(
            MemoryWikiImportRunPathStateRecord(
                vault_root_key=vault_root_key,
                run_id=record.run_id,
                index=index,
                path=path,
                kind="created-path",
            )
        )
    for index, entry in enumerate(record.updated_paths):
        rows.append(
            MemoryWikiImportRunPathStateRecord(
                vault_root_key=vault_root_key,
                run_id=record.run_id,
                index=index,
                path=entry.path,
                kind="updated-path",
                snapshot_path=entry.snapshot_path,
            )
        )
    return rows


def _record_to_dict(record: StateRecord) -> dict[str, Any]:
    """Serialize a state record to a JSON-friendly dict.

    Mirrors the OpenClaw
    ``MemoryWikiImportRunMetaStateRecord`` /
    ``MemoryWikiImportRunPathStateRecord``
    JSON shape (with the meta row carrying
    ``version: 1`` + ``importType: "chatgpt"``
    so the same row can be re-parsed via
    ``_normalize_run_record``).
    """
    if isinstance(record, MemoryWikiImportRunMetaStateRecord):
        out: dict[str, Any] = {
            "version": 1,
            "kind": "meta",
            "vaultRootKey": record.vault_root_key,
            "runId": record.run_id,
            "importType": record.import_type,
            "exportPath": record.export_path,
            "sourcePath": record.source_path,
            "appliedAt": record.applied_at,
            "conversationCount": record.conversation_count,
            "createdCount": record.created_count,
            "updatedCount": record.updated_count,
            "skippedCount": record.skipped_count,
        }
        if record.rolled_back_at is not None:
            out["rolledBackAt"] = record.rolled_back_at
        return out
    out = {
        "kind": record.kind,
        "vaultRootKey": record.vault_root_key,
        "runId": record.run_id,
        "index": record.index,
        "path": record.path,
    }
    if record.snapshot_path is not None:
        out["snapshotPath"] = record.snapshot_path
    return out


def _read_entry_value(entry: Any) -> Any:
    """Read the ``value`` field from a store entry (dict or PluginStateEntry)."""
    if isinstance(entry, dict):
        return entry.get("value")
    return getattr(entry, "value", None)


def _read_entry_key(entry: Any) -> str:
    """Read the ``key`` field from a store entry (dict or PluginStateEntry)."""
    if isinstance(entry, dict):
        raw = entry.get("key")
        if isinstance(raw, str):
            return raw
        return ""
    raw = getattr(entry, "key", None)
    return raw if isinstance(raw, str) else ""


# ── public store API ──────────────────────────────────────


class MemoryWikiImportRunStateStore:
    """The store API exposed to callers.

    Mirrors the OpenClaw
    ``MemoryWikiImportRunStateStore`` shape.
    The actual persistence is delegated to
    the underlying
    :class:`PluginStateKeyedStore`.
    """

    def __init__(self, store: PluginStateKeyedStore[dict[str, Any]]) -> None:
        self._store = store

    def read(self, vault_root: str, run_id: str) -> ChatGptImportRunRecord | None:
        """Read one import-run record.

        Mirrors OpenClaw's ``store.read``. Looks
        up the meta row, then collects all
        matching path rows.
        """
        vault_root_key = _resolve_vault_root_key(vault_root)
        meta_row = self._store.lookup(_resolve_state_entry_key(vault_root_key, run_id))
        meta_record = _normalize_meta_record(meta_row)
        if meta_record is None or meta_record.vault_root_key != vault_root_key:
            return None
        path_rows: list[MemoryWikiImportRunPathStateRecord] = []
        for entry in self._store.entries():
            value = _read_entry_value(entry)
            path_record = _normalize_path_record(value)
            if path_record is None:
                continue
            if path_record.vault_root_key == vault_root_key and path_record.run_id == run_id:
                path_rows.append(path_record)
        return _compose_run_record(meta_record, path_rows)

    def write(self, vault_root: str, record: ChatGptImportRunRecord) -> None:
        """Upsert one import-run record.

        Mirrors OpenClaw's ``store.write``.
        Replaces the meta row + every path row
        in a single transaction-style update.
        """
        vault_root_key = _resolve_vault_root_key(vault_root)
        self._store.register(
            _resolve_state_entry_key(vault_root_key, record.run_id),
            _record_to_dict(_to_meta_record(vault_root_key, record)),
        )
        next_path_keys: set[str] = set()
        for path_record in _to_path_records(vault_root_key, record):
            key = _resolve_path_state_entry_key(
                vault_root_key=vault_root_key,
                run_id=record.run_id,
                kind=path_record.kind,
                index=path_record.index,
                path=path_record.path,
            )
            next_path_keys.add(key)
            self._store.register(key, _record_to_dict(path_record))
        for entry in self._store.entries():
            value = _read_entry_value(entry)
            path_record = _normalize_path_record(value)
            if path_record is None:
                continue
            if path_record.vault_root_key == vault_root_key and path_record.run_id == record.run_id:
                entry_key = _read_entry_key(entry)
                if entry_key and entry_key not in next_path_keys:
                    self._store.delete(entry_key)

    def list(self, vault_root: str) -> list[ChatGptImportRunRecord]:
        """Return every import-run record for ``vault_root``."""
        vault_root_key = _resolve_vault_root_key(vault_root)
        meta_rows: dict[str, MemoryWikiImportRunMetaStateRecord] = {}
        path_rows: list[MemoryWikiImportRunPathStateRecord] = []
        for entry in self._store.entries():
            value = _read_entry_value(entry)
            meta = _normalize_meta_record(value)
            if meta is not None and meta.vault_root_key == vault_root_key:
                meta_rows[meta.run_id] = meta
                continue
            path_record = _normalize_path_record(value)
            if path_record is not None and path_record.vault_root_key == vault_root_key:
                path_rows.append(path_record)
        return [
            _compose_run_record(
                meta,
                [row for row in path_rows if row.run_id == meta.run_id],
            )
            for meta in meta_rows.values()
        ]

    def row_count(self) -> int:
        """Return the total number of rows in the store.

        Used by the doctor migration check to
        surface how much data the keyed store
        holds.
        """
        return len(self._store.entries())


def _default_keyed_store_factory() -> PluginStateKeyedStore[dict[str, Any]]:
    """Build a default in-memory keyed store for the import-runs namespace."""
    return open_plugin_state_keyed_store(
        OpenKeyedStoreOptions(
            namespace=MEMORY_WIKI_IMPORT_RUN_STATE_NAMESPACE,
            max_entries=MEMORY_WIKI_IMPORT_RUN_STATE_MAX_ENTRIES,
        )
    )


def create_memory_wiki_import_run_state_store(
    open_keyed_store: Any | None = None,
) -> MemoryWikiImportRunStateStore:
    """Build a store bound to a keyed-store namespace.

    Mirrors OpenClaw's
    ``createMemoryWikiImportRunStateStore``.
    ``open_keyed_store`` is the OpenClaw
    ``openKeyedStore`` factory; the Python port
    uses the default in-memory fallback when
    it's ``None``.
    """
    if open_keyed_store is None:
        store = _default_keyed_store_factory()
    else:
        store = open_keyed_store(
            OpenKeyedStoreOptions(
                namespace=MEMORY_WIKI_IMPORT_RUN_STATE_NAMESPACE,
                max_entries=MEMORY_WIKI_IMPORT_RUN_STATE_MAX_ENTRIES,
            )
        )
    return MemoryWikiImportRunStateStore(store)


# ── in-memory fallback ────────────────────────────────────


_memory_import_runs_by_vault: dict[str, dict[str, ChatGptImportRunRecord]] = {}


def _memory_import_runs(vault_root: str) -> dict[str, ChatGptImportRunRecord]:
    return _memory_import_runs_by_vault.setdefault(vault_root, {})


def create_memory_fallback_import_run_store() -> MemoryWikiImportRunStateStore:
    """Return the in-memory fallback store.

    Mirrors OpenClaw's
    ``createMemoryFallbackImportRunStore``.
    The store is backed by a module-level
    ``dict`` so it survives across calls
    within a single process; tests can
    reset it via
    :func:`reset_memory_wiki_import_run_state_for_tests`.
    """
    return _InMemoryImportRunStateStore()


class _InMemoryImportRunStateStore(MemoryWikiImportRunStateStore):
    """An in-memory implementation of the import-run store.

    Bypasses the keyed store and uses the
    module-level ``_memory_import_runs_by_vault``
    dict directly. Used when the host hasn't
    configured a real store (e.g. in tests).
    """

    def __init__(self) -> None:
        # Skip the parent's ``__init__`` (we
        # don't need the keyed store).
        pass

    def read(self, vault_root: str, run_id: str) -> ChatGptImportRunRecord | None:
        record = _memory_import_runs(vault_root).get(run_id)
        return _clone_run_record(record) if record is not None else None

    def write(self, vault_root: str, record: ChatGptImportRunRecord) -> None:
        _memory_import_runs(vault_root)[record.run_id] = _clone_run_record(record)

    def list(self, vault_root: str) -> list[ChatGptImportRunRecord]:
        return [_clone_run_record(record) for record in _memory_import_runs(vault_root).values()]

    def row_count(self) -> int:
        total = 0
        for records in _memory_import_runs_by_vault.values():
            for record in records.values():
                total += 1 + len(record.created_paths) + len(record.updated_paths)
        return total


# ── module-level configured store ─────────────────────────


_configured_import_run_store: MemoryWikiImportRunStateStore | None = None


def configure_memory_wiki_import_run_state_store(
    store: MemoryWikiImportRunStateStore | None,
) -> None:
    """Configure the process-wide import-run store.

    Mirrors OpenClaw's
    ``configureMemoryWikiImportRunStateStore``.
    ``None`` resets to the in-memory fallback.
    """
    global _configured_import_run_store  # noqa: PLW0603 — process-wide SDK config
    _configured_import_run_store = store


def _resolve_import_run_store(
    store: MemoryWikiImportRunStateStore | None = None,
) -> MemoryWikiImportRunStateStore:
    if store is not None:
        return store
    if _configured_import_run_store is not None:
        return _configured_import_run_store
    return create_memory_fallback_import_run_store()


def read_memory_wiki_import_run_record(
    vault_root: str,
    run_id: str,
    store: MemoryWikiImportRunStateStore | None = None,
) -> ChatGptImportRunRecord | None:
    """Read one import-run record.

    Mirrors OpenClaw's
    ``readMemoryWikiImportRunRecord``.
    """
    return _resolve_import_run_store(store).read(vault_root, run_id)


def write_memory_wiki_import_run_record(
    vault_root: str,
    record: ChatGptImportRunRecord,
    store: MemoryWikiImportRunStateStore | None = None,
) -> None:
    """Upsert one import-run record.

    Mirrors OpenClaw's
    ``writeMemoryWikiImportRunRecord``.
    """
    _resolve_import_run_store(store).write(vault_root, record)


def list_memory_wiki_import_run_records(
    vault_root: str,
    store: MemoryWikiImportRunStateStore | None = None,
) -> list[ChatGptImportRunRecord]:
    """List every import-run record for ``vault_root``.

    Mirrors OpenClaw's
    ``listMemoryWikiImportRunRecords``.
    """
    return _resolve_import_run_store(store).list(vault_root)


def count_memory_wiki_import_run_state_rows(
    store: MemoryWikiImportRunStateStore | None = None,
) -> int:
    """Return the total row count (test/doctor helper).

    Mirrors OpenClaw's
    ``countMemoryWikiImportRunStateRows``.
    """
    return _resolve_import_run_store(store).row_count()


# ── legacy file reads ─────────────────────────────────────


def resolve_memory_wiki_import_runs_dir(vault_root: str) -> str:
    """Return the legacy import-runs directory.

    Mirrors OpenClaw's
    ``resolveMemoryWikiImportRunsDir``.
    """
    return os.path.join(vault_root, ".openclaw-wiki", "import-runs")


def _read_one_legacy_record(
    json_path: Path,
) -> ChatGptImportRunRecord | None:
    try:
        raw = json_path.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        import json as _json

        parsed: Any = _json.loads(raw)
    except ValueError:
        return None
    return _normalize_run_record(parsed)


def read_legacy_memory_wiki_import_run_records(
    vault_root: str,
) -> list[ChatGptImportRunRecord]:
    """Read every legacy ``import-runs/*.json`` file under ``vault_root``.

    Mirrors OpenClaw's
    ``readLegacyMemoryWikiImportRunRecords``.
    The legacy format is the v0 per-file JSON
    format; the doctor migration in Phase
    4.3g uses this to bootstrap the keyed
    store.

    Files are read concurrently via a
    thread pool (capped at
    :data:`LEGACY_IMPORT_RUN_READ_CONCURRENCY`).
    Corrupt files are silently skipped
    (mirroring the OpenClaw ``pMapSkip``
    behavior).
    """

    import_runs_dir = Path(resolve_memory_wiki_import_runs_dir(vault_root))
    if not import_runs_dir.exists():
        return []
    paths = [
        child for child in import_runs_dir.iterdir() if child.is_file() and child.suffix == ".json"
    ]
    if not paths:
        return []
    out: list[ChatGptImportRunRecord] = []
    with ThreadPoolExecutor(
        max_workers=min(LEGACY_IMPORT_RUN_READ_CONCURRENCY, len(paths)),
    ) as pool:
        for record in pool.map(_read_one_legacy_record, paths):
            if record is not None:
                out.append(record)
    return out


def reset_memory_wiki_import_run_state_for_tests() -> None:
    """Reset module-level state (test-only helper).

    Clears the configured store + the
    in-memory fallback + the legacy file
    cache so subsequent tests start from a
    clean slate. Production code MUST NOT
    call this.
    """
    global _configured_import_run_store, _memory_import_runs_by_vault  # noqa: PLW0603 — test-only state
    _configured_import_run_store = None
    _memory_import_runs_by_vault = {}


__all__ = [
    "LEGACY_IMPORT_RUN_READ_CONCURRENCY",
    "MEMORY_WIKI_IMPORT_RUN_STATE_MAX_ENTRIES",
    "MEMORY_WIKI_IMPORT_RUN_STATE_NAMESPACE",
    "SUPPORTED_IMPORT_TYPES",
    "ChatGptImportRunEntry",
    "ChatGptImportRunRecord",
    "MemoryWikiImportRunMetaStateRecord",
    "MemoryWikiImportRunPathStateRecord",
    "MemoryWikiImportRunStateStore",
    "configure_memory_wiki_import_run_state_store",
    "count_memory_wiki_import_run_state_rows",
    "create_memory_fallback_import_run_store",
    "create_memory_wiki_import_run_state_store",
    "list_memory_wiki_import_run_records",
    "read_legacy_memory_wiki_import_run_records",
    "read_memory_wiki_import_run_record",
    "reset_memory_wiki_import_run_state_for_tests",
    "resolve_memory_wiki_import_runs_dir",
    "write_memory_wiki_import_run_record",
]
