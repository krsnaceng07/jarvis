"""memory_core.dreaming_state — SQLite-backed plugin state for the dreaming pipeline.

OpenClaw parity: mirrors ``extensions/memory-core/src/dreaming-state.ts``.
7 state namespaces + workspace-keyed CRUD helpers.

The dreaming pipeline uses these stores for:
- daily / session ingestion state (per-day, per-session file tracking)
- short-term recall entries
- phase signal metadata
- meta state (last-run timestamps, etc.)
- per-workspace lock entries (for cron concurrency control)
"""
from __future__ import annotations

import hashlib
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Generic, TypeVar

# 7 namespace constants — match OpenClaw exactly
DREAMING_DAILY_INGESTION_NAMESPACE = "dreaming-daily-ingestion"
DREAMING_SESSION_INGESTION_FILES_NAMESPACE = "dreaming-session-ingestion-files"
DREAMING_SESSION_INGESTION_SEEN_NAMESPACE = "dreaming-session-ingestion-seen"
SHORT_TERM_RECALL_NAMESPACE = "short-term-recall"
SHORT_TERM_PHASE_SIGNAL_NAMESPACE = "short-term-phase-signals"
SHORT_TERM_META_NAMESPACE = "short-term-meta"
SHORT_TERM_LOCK_NAMESPACE = "short-term-locks"

# Capacity constants — match OpenClaw exactly
_DREAMING_WORKSPACE_STATE_MAX_ENTRIES = 50_000
SHORT_TERM_LOCK_MAX_ENTRIES = 4_096
SESSION_SEEN_HASHES_PER_CHUNK = 512

MEMORY_CORE_PLUGIN_ID = "memory-core"

# ── OpenKeyedStore integration ────────────────────────────────────────────
# The JARVIS plugin_sdk exposes ``openKeyedStore`` via the runtime.state
# namespace. The port takes a ``MemoryCoreOpenKeyedStore`` factory — same
# shape as OpenClaw's. The host calls ``configure_memory_core_dreaming_state``
# once at plugin init to wire it up.

# The SDK's PluginStateKeyedStore is protocol-shaped; we don't import the
# concrete class here to keep this module standalone. The Protocol below
# mirrors the SDK's interface used by dreaming-state.ts.
T = TypeVar("T")


class _KeyedStoreLike(Generic[T]):
    """Duck-typed mirror of ``PluginStateKeyedStore<T>``.

    The SDK's actual class lives in
    ``packages.plugin_sdk.src.jarvis_sdk.plugin_state_keyed_store``.
    OpenClaw's port is generic; the consumer (the host's runtime.state)
    supplies an implementation that matches this Protocol.
    """

    def entries(self) -> list[tuple[str, T]]: ...
    def register(self, key: str, value: T) -> None: ...
    def delete(self, key: str) -> None: ...
    def clear(self) -> None: ...


# Mirrors the SDK's ``OpenKeyedStoreOptions`` (only the fields we use).
@dataclass(frozen=True)
class OpenKeyedStoreOptions:
    namespace: str
    max_entries: int | None = None


MemoryCoreOpenKeyedStore = Callable[[OpenKeyedStoreOptions], _KeyedStoreLike]

_configured_open_keyed_store: MemoryCoreOpenKeyedStore | None = None


def configure_memory_core_dreaming_state(
    open_keyed_store: MemoryCoreOpenKeyedStore,
) -> None:
    """Wire the host's keyed store factory into the dreaming state.

    Mirrors OpenClaw's ``configureMemoryCoreDreamingState``. Must be called
    once during plugin registration before any ``read`` / ``write`` /
    ``clear`` call.
    """
    global _configured_open_keyed_store
    _configured_open_keyed_store = open_keyed_store


def open_memory_core_state_store(
    options: OpenKeyedStoreOptions,
) -> _KeyedStoreLike:
    """Open (or re-open) a state store for the given namespace.

    Mirrors OpenClaw's ``openMemoryCoreStateStore``.
    """
    if _configured_open_keyed_store is None:
        raise RuntimeError("memory-core dreaming SQLite state store is not configured")
    return _configured_open_keyed_store(options)


# ── Workspace key normalization ───────────────────────────────────────────


def normalize_memory_core_workspace_key(workspace_dir: str) -> str:
    """Normalize a workspace path into a stable key string.

    Mirrors OpenClaw's ``normalizeMemoryCoreWorkspaceKey``:
    1. ``path.resolve`` (canonicalize, remove symlinks/``./`` etc.)
    2. Replace backslashes with forward slashes
    3. On Windows, lowercase the result (filesystem is case-insensitive)

    Used as input to the SHA-256 that produces the workspace state key.
    """
    resolved = str(Path(workspace_dir).resolve()).replace("\\", "/")
    if sys.platform == "win32":
        return resolved.lower()
    return resolved


def memory_core_workspace_state_key(workspace_dir: str) -> str:
    """Return the SHA-256 (hex) of the normalized workspace key.

    Mirrors OpenClaw's ``memoryCoreWorkspaceStateKey``. Each workspace gets
    a 64-char hex key used to namespace all state entries for that workspace.
    """
    return hashlib.sha256(
        normalize_memory_core_workspace_key(workspace_dir).encode("utf-8")
    ).hexdigest()


def memory_core_workspace_entry_key(workspace_dir: str, logical_key: str) -> str:
    """Return the keyed-store key for a single entry within a workspace.

    Mirrors OpenClaw's ``memoryCoreWorkspaceEntryKey``. Format:
    ``<workspaceHexKey>:<itemHexKey>``. Both halves are SHA-256 hex of
    their respective inputs (workspace normalized, logical_key as-is).
    """
    workspace_key = memory_core_workspace_state_key(workspace_dir)
    item_key = hashlib.sha256(logical_key.encode("utf-8")).hexdigest()
    return f"{workspace_key}:{item_key}"


def memory_core_state_reference(namespace: str, workspace_dir: str) -> str:
    """Return the canonical state reference string for diagnostics.

    Mirrors OpenClaw's ``memoryCoreStateReference``. Format:
    ``plugin-state:<pluginId>/<namespace>/<workspaceHexKey>``.
    """
    return f"plugin-state:{MEMORY_CORE_PLUGIN_ID}/{namespace}/{memory_core_workspace_state_key(workspace_dir)}"


# ── WorkspaceValue envelope ──────────────────────────────────────────────
# OpenClaw wraps every state value in a typed envelope so:
# 1. The keyed store can carry any ``T`` payload
# 2. Each value carries the workspaceKey + workspaceDir + key it belongs to
#    (so cross-workspace reads can be filtered defensively)
# 3. The ``version: 1`` lets us migrate the envelope shape later
#
# The JavaScript side stores raw JSON; in Python we use a plain dict so
# the SDK's keyed store (which JSON-serializes) can round-trip it.

WorkspaceValue = dict[str, Any]


def _make_workspace_value(
    workspace_key: str, workspace_dir: str, key: str, value: Any
) -> WorkspaceValue:
    return {
        "version": 1,
        "workspaceKey": workspace_key,
        "workspaceDir": str(Path(workspace_dir).resolve()),
        "key": key,
        "value": value,
    }


def _open_workspace_store(namespace: str) -> _KeyedStoreLike:
    return open_memory_core_state_store(
        OpenKeyedStoreOptions(
            namespace=namespace,
            max_entries=_DREAMING_WORKSPACE_STATE_MAX_ENTRIES,
        )
    )


# ── Read / write / clear ──────────────────────────────────────────────────


def read_memory_core_workspace_entries(
    namespace: str, workspace_dir: str
) -> list[tuple[str, Any]]:
    """Read all entries for the given workspace from the named namespace.

    Mirrors OpenClaw's ``readMemoryCoreWorkspaceEntries``. Returns a list
    of ``(logical_key, value)`` pairs. Filters by ``workspaceKey`` prefix
    AND defensively re-checks the embedded ``workspaceKey`` field (the
    latter is what makes reads safe even if the keyed store returns
    cross-workspace keys by mistake).
    """
    workspace_key = memory_core_workspace_state_key(workspace_dir)
    prefix = f"{workspace_key}:"
    raw_entries = _open_workspace_store(namespace).entries()
    out: list[tuple[str, Any]] = []
    for key, envelope in raw_entries:
        if not key.startswith(prefix):
            continue
        if not isinstance(envelope, dict):
            continue
        if envelope.get("workspaceKey") != workspace_key:
            continue
        out.append((envelope["key"], envelope["value"]))
    return out


def write_memory_core_workspace_entries(
    namespace: str, workspace_dir: str, entries: list[tuple[str, Any]]
) -> None:
    """Replace the workspace's entries in the named namespace.

    Mirrors OpenClaw's ``writeMemoryCoreWorkspaceEntries``: writes each
    new entry, then prunes any existing entries in the workspace prefix
    that weren't in the new set. This is the "replace set" pattern used
    by the phase signals and short-term recall.
    """
    store = _open_workspace_store(namespace)
    workspace_key = memory_core_workspace_state_key(workspace_dir)
    prefix = f"{workspace_key}:"
    replacement_keys: set[str] = set()
    for logical_key, value in entries:
        state_key = memory_core_workspace_entry_key(workspace_dir, logical_key)
        replacement_keys.add(state_key)
        store.register(
            state_key,
            _make_workspace_value(workspace_key, workspace_dir, logical_key, value),
        )
    # Prune stale entries.
    for key, _envelope in store.entries():
        if key.startswith(prefix) and key not in replacement_keys:
            store.delete(key)


def write_memory_core_workspace_entry(
    namespace: str, workspace_dir: str, key: str, value: Any
) -> None:
    """Write a single entry to the workspace's namespace.

    Mirrors OpenClaw's ``writeMemoryCoreWorkspaceEntry``. Unlike
    ``write_memory_core_workspace_entries``, this does NOT prune other
    entries — it's a single-key add/update.
    """
    workspace_key = memory_core_workspace_state_key(workspace_dir)
    _open_workspace_store(namespace).register(
        memory_core_workspace_entry_key(workspace_dir, key),
        _make_workspace_value(workspace_key, workspace_dir, key, value),
    )


def clear_memory_core_workspace_namespace(namespace: str, workspace_dir: str) -> None:
    """Delete all entries for the given workspace from the named namespace.

    Mirrors OpenClaw's ``clearMemoryCoreWorkspaceNamespace``.
    """
    store = _open_workspace_store(namespace)
    workspace_key = memory_core_workspace_state_key(workspace_dir)
    prefix = f"{workspace_key}:"
    for key, _envelope in store.entries():
        if key.startswith(prefix):
            store.delete(key)


__all__ = [
    # 7 namespace constants
    "DREAMING_DAILY_INGESTION_NAMESPACE",
    "DREAMING_SESSION_INGESTION_FILES_NAMESPACE",
    "DREAMING_SESSION_INGESTION_SEEN_NAMESPACE",
    "SHORT_TERM_RECALL_NAMESPACE",
    "SHORT_TERM_PHASE_SIGNAL_NAMESPACE",
    "SHORT_TERM_META_NAMESPACE",
    "SHORT_TERM_LOCK_NAMESPACE",
    # Capacity constants
    "SHORT_TERM_LOCK_MAX_ENTRIES",
    "SESSION_SEEN_HASHES_PER_CHUNK",
    # Configuration + opening
    "configure_memory_core_dreaming_state",
    "open_memory_core_state_store",
    "OpenKeyedStoreOptions",
    "MemoryCoreOpenKeyedStore",
    # Workspace key helpers
    "normalize_memory_core_workspace_key",
    "memory_core_workspace_state_key",
    "memory_core_workspace_entry_key",
    "memory_core_state_reference",
    # CRUD
    "read_memory_core_workspace_entries",
    "write_memory_core_workspace_entries",
    "write_memory_core_workspace_entry",
    "clear_memory_core_workspace_namespace",
    # Type alias
    "WorkspaceValue",
]
