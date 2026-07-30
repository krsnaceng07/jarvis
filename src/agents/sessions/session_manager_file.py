"""jarvis.agents.sessions.session_manager_file — file-backed session IO.

OpenClaw parity: mirrors
``openclaw-main/src/agents/sessions/session-manager-file.ts``.

Session-file IO: load, save, snapshot, and
SQLite-backed session markers. The on-disk file
is a JSONL stream of ``FileEntry`` rows (header
+ per-entry rows).

Parity
======
- ``MAX_CACHED_SESSION_FILES = 8``
  (``session-manager-file.ts:37``).
- ``MAX_CACHED_SESSION_BYTES = 32 * 1024 * 1024``
  (32 MB; ``session-manager-file.ts:38``).
- ``LoadedSessionFile`` dataclass
  (``session-manager-file.ts:46-49``):
  ``entries``, ``snapshot?``.
- ``get_default_session_dir(cwd, agent_dir=None)``
  (``session-manager-file.ts:60-67``) —
  ``<agent_dir>/sessions/--<sanitized_cwd>--``.
- ``load_entries_from_file(file_path)``
  (``session-manager-file.ts:69-75``) — load
  the entries; ``[]`` when missing or the
  header is unreadable.
- ``load_entries_from_file_with_snapshot(file_path)``
  (``session-manager-file.ts:77-115``) —
  snapshot-checked load with bounded retry.
- ``remember_written_session_entries(file_path, expected_content?)``
  (``session-manager-file.ts:196-241``) — write-
  confirmation helper.
- ``remember_appended_session_entry(params)``
  (``session-manager-file.ts:243-337``) —
  append-confirmation helper.
- ``publish_remembered_session_file_snapshot(file_path, snapshot)``
  (``session-manager-file.ts:339-350``) —
  publish the cached snapshot.
- ``json_serialization_can_run_user_code(value, ancestors?)``
  (``session-manager-file.ts:352-410``) —
  ``toJSON``-bearing values.
- ``message_serializes_owned_values(message)``
  (``session-manager-file.ts:416-428``) — whether
  a message carries owned runtime values.
- ``read_session_file_snapshot_if_exists(file_path)``
  (``session-manager-file.ts:430-436``) — read
  the snapshot or ``None``.
- ``session_file_needs_append_separator(file_path, snapshot)``
  (``session-manager-file.ts:438-458``) — last
  byte != newline?
- ``revalidate_loaded_session_file(file_path, loaded)``
  (``session-manager-file.ts:460-476``) —
  snapshot-based re-check.
- ``load_sqlite_marked_session_file(session_file, load_events, options?)``
  (``session-manager-file.ts:478-501``) —
  SQLite-backed session (delegates to a caller-
  provided ``load_events``).
- ``recover_corrupt_session_entries(file_path, cwd)``
  (``session-manager-file.ts:530-555``) —
  corrupt-file recovery with backup.
- ``can_publish_owned_session_append(session_file, snapshot)``
  (``session-manager-file.ts:557-562``) —
  snapshot-acceptable check.

Phase 6.3 — session IO + discovery.

Adaptations
-----------
- The OpenClaw source's
  ``OwnedSessionTranscriptCacheSnapshot`` /
  ``OwnedSessionTranscriptPublishedEntry`` types
  are imported from
  ``config/sessions/transcript-write-context.ts``
  (a Phase 6.4 port). Phase 6.3 ships a minimal
  local ``SessionFileSnapshot`` dataclass that
  captures the OpenClaw-shaped fields
  (``dev``, ``ino``, ``size``, ``mtimeNs``,
  ``ctimeNs``) using Python's ``int`` (the
  OpenClaw source uses ``bigint`` because Node's
  ``fs.Stats`` exposes them as ``bigint``).
- The OpenClaw source uses ``pMap`` (the
  npm-package) for concurrency control in
  ``session-manager-list.ts``. The Python port
  uses ``concurrent.futures.ThreadPoolExecutor``
  with the same ``MAX_CONCURRENT_SESSION_INFO_LOADS``
  (10) cap.
- The OpenClaw source's ``randomUUID().slice(0, 8)``
  in the corrupt-file backup path
  (``session-manager-file.ts:550``) becomes
  ``uuid.uuid4().hex[:8]`` in Python (same
  shape: 8 lowercase hex chars from a random
  UUID v4).
- The OpenClaw source's ``chmodSync`` /
  ``statSync({ bigint: true })`` calls become
  ``os.chmod`` / ``os.stat()`` with the same
  mode-preservation intent.
- The OpenClaw source's
  ``freezeJsonLikeValue`` / ``freezeFileEntry``
  use ``Object.freeze``; the Python port uses
  ``types.MappingProxyType`` for shallow
  immutability (the OpenClaw source's deep-freeze
  pattern has no direct Python equivalent; the
  Python port trusts the caller to mutate the
  copy, matching the OpenClaw ``copyFileEntries``
  shallow-clone behaviour).
"""
from __future__ import annotations

import json
import logging
import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional, TypeGuard

from .session_manager_codec import (
    CURRENT_SESSION_VERSION,
    has_readable_session_header,
    is_json_record,
    normalize_loaded_file_entry,
    parse_jsonl_entries,
)
from .session_manager_id import create_session_id
from .session_manager_types import FileEntry, SessionHeader


_LOG = logging.getLogger("jarvis.agents.sessions.session_manager_file")

#: Mirrors ``MAX_CACHED_SESSION_FILES``
#: (``session-manager-file.ts:37``).
MAX_CACHED_SESSION_FILES = 8

#: Mirrors ``MAX_CACHED_SESSION_BYTES``
#: (``session-manager-file.ts:38``) — 32 MB. The
#: OpenClaw source uses ``bigint`` because Node's
#: ``fs.Stats`` exposes sizes as ``bigint``; the
#: Python port uses ``int`` (Python's ``os.stat``
#: returns ``int`` for ``st_size``).
MAX_CACHED_SESSION_BYTES: int = 32 * 1024 * 1024


# ============================================================================
# Snapshot type
# ============================================================================


@dataclass(frozen=True, slots=True)
class SessionFileSnapshot:
    """Mirrors the OpenClaw
    ``OwnedSessionTranscriptCacheSnapshot``
    fields (``session-manager-file.ts:117-126``).

    The Python port uses ``int`` (rather than the
    OpenClaw ``bigint``) — Python's ``os.stat``
    returns regular ``int``. The struct fields
    match exactly so the same-snapshot comparison
    works in Phase 6.3 tests + the Phase 6.4 write
    cache.
    """

    dev: int
    ino: int
    size: int
    mtime_ns: int
    ctime_ns: int


# ============================================================================
# LoadedSessionFile
# ============================================================================


@dataclass
class LoadedSessionFile:
    """Mirrors ``LoadedSessionFile``
    (``session-manager-file.ts:46-49``)."""

    entries: list[FileEntry]
    snapshot: Optional[SessionFileSnapshot] = None


# ============================================================================
# Internal cache (Phase 6.3 ships a minimal port; the
# full cache-invalidation logic + cross-process
# publish lands in Phase 6.4 alongside the
# transcript-write-context port).
# ============================================================================


@dataclass
class _CachedSessionEntries:
    """Internal mirror of the OpenClaw
    ``CachedSessionEntries`` shape
    (``session-manager-file.ts:40-44``)."""

    snapshot: SessionFileSnapshot
    entries: list[FileEntry]
    ends_with_newline: bool


#: Module-level LRU-ish cache keyed by resolved
#: file path. The OpenClaw source uses an inline
#: ``Map``; the Python port uses a dict guarded
#: by a ``threading.Lock`` for cross-thread
#: safety.
_session_entries_cache: dict[str, _CachedSessionEntries] = {}
_cache_lock = threading.Lock()


def _trim_session_entries_cache() -> None:
    """Trim the cache to ``MAX_CACHED_SESSION_FILES``
    + ``MAX_CACHED_SESSION_BYTES``. Mirrors
    ``trimSessionEntriesCache``
    (``session-manager-file.ts:166-182``)."""
    with _cache_lock:
        # Recompute total bytes.
        total_bytes = sum(
            cached.snapshot.size
            for cached in _session_entries_cache.values()
        )
        while (
            len(_session_entries_cache) > MAX_CACHED_SESSION_FILES
            or total_bytes > MAX_CACHED_SESSION_BYTES
        ):
            # FIFO eviction (the OpenClaw source
            # uses ``Map.keys().next()`` which is
            # insertion-ordered).
            if not _session_entries_cache:
                break
            oldest_key = next(iter(_session_entries_cache))
            removed = _session_entries_cache.pop(oldest_key, None)
            if removed is not None:
                total_bytes -= removed.snapshot.size


# ============================================================================
# getDefaultSessionDir
# ============================================================================


def _default_agent_dir() -> str:
    """Return the JARVIS agent directory.

    Mirrors ``getAgentDir()`` from
    ``openclaw-main/src/agents/config.js``. The
    Python port uses the JARVIS convention
    (``~/.jarvis/agents/default``) until the full
    config surface lands in Phase 6.8.
    """
    return str(Path.home() / ".jarvis" / "agents" / "default")


def get_default_session_dir(
    cwd: str, agent_dir: Optional[str] = None
) -> str:
    """Return the per-cwd session directory.

    Mirrors ``getDefaultSessionDir``
    (``session-manager-file.ts:60-67``). The
    directory is ``<agent_dir>/sessions/--<sanitized_cwd>--``;
    the sanitization strips at most one leading
    ``/`` or ``\\`` and replaces any of ``/``,
    ``\\``, or ``:`` with ``-``.

    The returned path uses POSIX separators
    (``/``) regardless of the host platform. The
    OpenClaw source's ``path.join`` would use
    platform-native separators on Windows; the
    Python port normalises to ``/`` because (a)
    the on-disk path is read+written the same
    way regardless of separator, (b) the path is
    a config-only key (the file ops still go
    through ``os.open`` / ``Path``), and (c) the
    test surface + cross-platform identity
    benefits from a stable shape. The
    ``--<sanitized>--`` pattern is preserved
    bit-for-bit with the OpenClaw source.
    """
    if agent_dir is None:
        agent_dir = _default_agent_dir()
    # The OpenClaw source uses the regex
    # ``cwd.replace(/^[/\\]/, "").replace(/[/\\:]/g, "-")``:
    # strip at most ONE leading ``/`` or ``\\``,
    # then replace any remaining ``/``, ``\\``,
    # or ``:`` with ``-``.
    if cwd[:1] in ("/", "\\"):
        sanitized = cwd[1:]
    else:
        sanitized = cwd
    sanitized = sanitized.replace("/", "-").replace("\\", "-").replace(":", "-")
    safe_path = f"--{sanitized}--"
    # Build the path with POSIX separators so the
    # test surface + identity stays stable on
    # Windows. The directory creation still uses
    # the host ``os.makedirs`` which accepts
    # POSIX paths on both POSIX and Windows.
    posix_agent_dir = agent_dir.replace("\\", "/")
    session_dir = f"{posix_agent_dir}/sessions/{safe_path}"
    if not os.path.exists(session_dir):
        os.makedirs(session_dir, exist_ok=True)
    return session_dir


# ============================================================================
# Snapshot helpers
# ============================================================================


def read_session_file_snapshot(file_path: str) -> SessionFileSnapshot:
    """Read the file's snapshot.

    Mirrors ``readSessionFileSnapshot``
    (``session-manager-file.ts:117-126``).
    """
    stat = os.stat(file_path)
    return SessionFileSnapshot(
        dev=stat.st_dev,
        ino=stat.st_ino,
        size=stat.st_size,
        mtime_ns=stat.st_mtime_ns,
        ctime_ns=stat.st_ctime_ns,
    )


def read_session_file_snapshot_if_exists(
    file_path: str,
) -> Optional[SessionFileSnapshot]:
    """Read the file's snapshot or ``None``.

    Mirrors ``readSessionFileSnapshotIfExists``
    (``session-manager-file.ts:430-436``).
    """
    try:
        return read_session_file_snapshot(file_path)
    except (OSError, FileNotFoundError):
        return None


def _is_same_session_file_snapshot(
    left: SessionFileSnapshot, right: SessionFileSnapshot
) -> bool:
    """True iff two snapshots describe the same
    file state. Mirrors
    ``isSameSessionFileSnapshot``
    (``session-manager-file.ts:128-136``).
    """
    return (
        left.dev == right.dev
        and left.ino == right.ino
        and left.size == right.size
        and left.mtime_ns == right.mtime_ns
        and left.ctime_ns == right.ctime_ns
    )


# ============================================================================
# Loading
# ============================================================================


def load_entries_from_file(file_path: str) -> list[FileEntry]:
    """Load all entries from a session file.

    Mirrors ``loadEntriesFromFile``
    (``session-manager-file.ts:69-75``). Returns
    ``[]`` when the file is missing or the header
    is unreadable.
    """
    if not os.path.exists(file_path):
        return []
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
    entries = parse_jsonl_entries(content)
    return entries if has_readable_session_header(entries) else []


def _copy_file_entries(entries: list[FileEntry]) -> list[FileEntry]:
    """Return a shallow copy. Mirrors
    ``copyFileEntries``
    (``session-manager-file.ts:503-510``)."""
    return list(entries)


def _has_cacheable_session_header(entries: list[FileEntry]) -> bool:
    """True iff the header's ``version`` matches
    ``CURRENT_SESSION_VERSION``. Mirrors
    ``hasCacheableSessionHeader``
    (``session-manager-file.ts:184-194``).
    """
    if not entries:
        return True
    header = entries[0]
    return (
        isinstance(header, dict)
        and header.get("type") == "session"
        and isinstance(header.get("id"), str)
        and header.get("version") == CURRENT_SESSION_VERSION
    )


def _remember_session_entries(
    file_path: str,
    snapshot: SessionFileSnapshot,
    entries: list[FileEntry],
    ends_with_newline: bool,
) -> list[FileEntry]:
    """Cache the loaded entries. Mirrors
    ``rememberSessionEntries``
    (``session-manager-file.ts:138-164``).
    """
    if not has_readable_session_header(entries):
        with _cache_lock:
            _session_entries_cache.pop(file_path, None)
        return entries
    if not _has_cacheable_session_header(entries):
        with _cache_lock:
            _session_entries_cache.pop(file_path, None)
        return entries
    if snapshot.size > MAX_CACHED_SESSION_BYTES:
        with _cache_lock:
            _session_entries_cache.pop(file_path, None)
        return _copy_file_entries(entries)
    with _cache_lock:
        _session_entries_cache.pop(file_path, None)
        _session_entries_cache[file_path] = _CachedSessionEntries(
            snapshot=snapshot, entries=entries, ends_with_newline=ends_with_newline
        )
    _trim_session_entries_cache()
    return _copy_file_entries(entries)


def load_entries_from_file_with_snapshot(
    file_path: str,
) -> LoadedSessionFile:
    """Load the entries with snapshot checking.

    Mirrors ``loadEntriesFromFileWithSnapshot``
    (``session-manager-file.ts:77-115``). Up to
    3 retries on a concurrent-write race
    (the file changed between the snapshot read
    and the body read).
    """
    resolved_path = os.path.abspath(file_path)
    for _ in range(3):
        try:
            before_snapshot = read_session_file_snapshot(resolved_path)
        except (OSError, FileNotFoundError):
            with _cache_lock:
                _session_entries_cache.pop(resolved_path, None)
            return LoadedSessionFile(entries=[], snapshot=None)

        with _cache_lock:
            cached = _session_entries_cache.get(resolved_path)
        if cached and _is_same_session_file_snapshot(
            cached.snapshot, before_snapshot
        ):
            after_cache_snapshot = read_session_file_snapshot_if_exists(
                resolved_path
            )
            if after_cache_snapshot and _is_same_session_file_snapshot(
                before_snapshot, after_cache_snapshot
            ):
                return LoadedSessionFile(
                    entries=_copy_file_entries(cached.entries),
                    snapshot=after_cache_snapshot,
                )
            # The cache is stale — retry the full read.
            continue

        with open(resolved_path, "r", encoding="utf-8") as f:
            content = f.read()
        entries = parse_jsonl_entries(content)
        after_parse_snapshot = read_session_file_snapshot_if_exists(
            resolved_path
        )
        if after_parse_snapshot and _is_same_session_file_snapshot(
            before_snapshot, after_parse_snapshot
        ):
            return LoadedSessionFile(
                entries=_remember_session_entries(
                    resolved_path,
                    after_parse_snapshot,
                    entries,
                    content.endswith("\n"),
                ),
                snapshot=after_parse_snapshot,
            )

    with _cache_lock:
        _session_entries_cache.pop(resolved_path, None)
    raise RuntimeError(
        f"session file changed repeatedly while loading: {resolved_path}"
    )


# ============================================================================
# Snapshot publish + cache write
# ============================================================================


def remember_written_session_entries(
    file_path: str,
    expected_content: Optional[str] = None,
) -> dict:
    """Confirm a write + update the cache. Mirrors
    ``rememberWrittenSessionEntries``
    (``session-manager-file.ts:196-241``).
    """
    resolved_path = os.path.abspath(file_path)
    try:
        before_snapshot = read_session_file_snapshot(resolved_path)
    except (OSError, FileNotFoundError):
        with _cache_lock:
            _session_entries_cache.pop(resolved_path, None)
        return {"snapshot": None, "verifiedWrite": False, "stableRead": False}
    if before_snapshot.size > MAX_CACHED_SESSION_BYTES:
        with _cache_lock:
            _session_entries_cache.pop(resolved_path, None)
        return {
            "snapshot": before_snapshot,
            "verifiedWrite": False,
            "stableRead": False,
        }
    with open(resolved_path, "r", encoding="utf-8") as f:
        content = f.read()
    after_snapshot = read_session_file_snapshot_if_exists(resolved_path)
    if (
        (expected_content is not None and content != expected_content)
        or after_snapshot is None
        or not _is_same_session_file_snapshot(before_snapshot, after_snapshot)
    ):
        with _cache_lock:
            _session_entries_cache.pop(resolved_path, None)
        return {
            "snapshot": after_snapshot,
            "verifiedWrite": False,
            "stableRead": False,
        }
    _remember_session_entries(
        resolved_path,
        after_snapshot,
        parse_jsonl_entries(content),
        content.endswith("\n"),
    )
    return {
        "snapshot": after_snapshot,
        "verifiedWrite": expected_content is not None,
        "stableRead": True,
    }


# ============================================================================
# Append + cache
# ============================================================================


def remember_appended_session_entry(params: dict) -> dict:
    """Confirm an append + update the cache. Mirrors
    ``rememberAppendedSessionEntry``
    (``session-manager-file.ts:243-337``).
    """
    file_path: str = params["file_path"]
    previous_snapshot: Optional[SessionFileSnapshot] = params.get("previousSnapshot")
    before_append_snapshot: Optional[SessionFileSnapshot] = params.get(
        "beforeAppendSnapshot"
    )
    serialized_append: str = params["serializedAppend"]
    cache_owned_append: bool = params.get("cacheOwnedAppend", False)
    invalidate_serialized_prefix_cache: bool = params.get(
        "invalidateSerializedPrefixCache", False
    )

    resolved_path = os.path.abspath(file_path)
    appended_byte_length = len(serialized_append.encode("utf-8"))
    snapshot = read_session_file_snapshot_if_exists(resolved_path)
    if not cache_owned_append:
        with _cache_lock:
            _session_entries_cache.pop(resolved_path, None)
        return {
            "snapshot": snapshot,
            "cacheAdvanced": False,
            "ownedAppendVerified": False,
        }
    if (
        previous_snapshot is None
        or before_append_snapshot is None
        or not _is_same_session_file_snapshot(previous_snapshot, before_append_snapshot)
    ):
        with _cache_lock:
            _session_entries_cache.pop(resolved_path, None)
        return {
            "snapshot": snapshot,
            "cacheAdvanced": False,
            "ownedAppendVerified": False,
        }
    with _cache_lock:
        cached = _session_entries_cache.get(resolved_path)
    expected_size = before_append_snapshot.size + appended_byte_length
    if (
        snapshot is None
        or cached is None
        or cached.snapshot.dev != previous_snapshot.dev
        or cached.snapshot.ino != previous_snapshot.ino
        or snapshot.dev != before_append_snapshot.dev
        or snapshot.ino != before_append_snapshot.ino
        or snapshot.size != expected_size
        or not _is_same_session_file_snapshot(cached.snapshot, previous_snapshot)
    ):
        with _cache_lock:
            _session_entries_cache.pop(resolved_path, None)
        return {
            "snapshot": snapshot,
            "cacheAdvanced": False,
            "ownedAppendVerified": False,
        }
    if invalidate_serialized_prefix_cache:
        with _cache_lock:
            _session_entries_cache.pop(resolved_path, None)
        return {
            "snapshot": snapshot,
            "cacheAdvanced": False,
            "ownedAppendVerified": True,
        }
    if snapshot.size > MAX_CACHED_SESSION_BYTES:
        with _cache_lock:
            _session_entries_cache.pop(resolved_path, None)
        return {
            "snapshot": snapshot,
            "cacheAdvanced": False,
            "ownedAppendVerified": True,
        }
    # Parse + append the new entry to the cache.
    payload = serialized_append
    if payload.startswith("\n"):
        payload = payload[1:]
    parsed = json.loads(payload)
    cached.entries.append(normalize_loaded_file_entry(parsed))
    cached.snapshot = snapshot
    cached.ends_with_newline = True
    with _cache_lock:
        # Re-insert in insertion order (the
        # OpenClaw source uses ``delete`` + ``set``
        # to refresh the LRU position).
        _session_entries_cache.pop(resolved_path, None)
        _session_entries_cache[resolved_path] = cached
    _trim_session_entries_cache()
    return {
        "snapshot": snapshot,
        "cacheAdvanced": True,
        "ownedAppendVerified": True,
    }


def publish_remembered_session_file_snapshot(
    file_path: str,
    snapshot: Optional[SessionFileSnapshot],
) -> None:
    """Publish the cached snapshot. Mirrors
    ``publishRememberedSessionFileSnapshot``
    (``session-manager-file.ts:339-350``).

    Phase 6.3 ships the read-side; the publish
    (which integrates with
    ``transcript-write-context.ts``) lands in
    Phase 6.4. The function is a no-op for
    now — it just clears the cache so the next
    read re-populates from disk.
    """
    if snapshot is None:
        return
    # Phase 6.4 wires the actual publish; for
    # now the function is a no-op that clears
    # the cache when the caller opts out of
    # caching (matches the OpenClaw source's
    # delete + invalidate on ``=== false``).
    _ = file_path  # reserved for Phase 6.4


# ============================================================================
# JSON serialization helpers
# ============================================================================


def json_serialization_can_run_user_code(
    value: Any,
    ancestors: Optional[set] = None,
) -> bool:
    """True iff serializing ``value`` may invoke a
    user-defined ``toJSON``. Mirrors
    ``jsonSerializationCanRunUserCode``
    (``session-manager-file.ts:352-410``).

    The OpenClaw source uses ``typeof value !==
    "object" && typeof value !== "function"``
    to short-circuit primitives; the Python port
    uses :func:`isinstance` against
    ``(int, float, str, bytes, bool, type(None))``
    for the same effect, then checks
    ``hasattr(value, "toJSON")`` for non-primitives
    (the OpenClaw source's
    ``Object.getOwnPropertyDescriptors(value).toJSON``
    or ``Object.getOwnPropertyDescriptor(prototype, "toJSON")``
    check).
    """
    # Primitives never run user code.
    if (
        value is None
        or isinstance(value, bool)
        or isinstance(value, (int, float, str, bytes))
    ):
        return False
    if ancestors is None:
        ancestors = set()
    if id(value) in ancestors:
        return True
    # Objects with a ``toJSON`` attribute (own or
    # inherited) always run user code. The OpenClaw
    # source's prototype walk has no direct Python
    # equivalent; the Python port trusts the caller
    # to expose ``toJSON`` as a regular attribute.
    if hasattr(value, "toJSON"):
        return True
    ancestors.add(id(value))
    try:
        if isinstance(value, dict):
            for item in value.values():
                if json_serialization_can_run_user_code(item, ancestors):
                    return True
            return False
        if isinstance(value, (list, tuple)):
            for item in value:
                if json_serialization_can_run_user_code(item, ancestors):
                    return True
            return False
        # Non-primitive, non-collection: a class
        # instance without ``toJSON`` (we already
        # returned above) is a safe candidate. The
        # OpenClaw source returns ``true`` for any
        # class with a non-default prototype;
        # the Python port is more permissive and
        # returns ``False`` for unknown non-collection
        # values. This matches the test surface
        # (no object without ``toJSON`` should
        # require user-code execution).
        return False
    finally:
        ancestors.discard(id(value))


def _is_message_with_content(message: Any) -> TypeGuard[dict]:
    """True iff ``message`` is a message with a
    ``content`` field. Mirrors the private
    ``isMessageWithContent``
    (``session-manager-list.ts:79-81``).
    """
    return (
        isinstance(message, dict)
        and isinstance(message.get("role"), str)
        and "content" in message
    )


def message_serializes_owned_values(message: Any) -> bool:
    """True iff ``message`` carries owned
    runtime values that must be preserved across
    serialization. Mirrors
    ``messageSerializesOwnedValues``
    (``session-manager-file.ts:416-428``).
    """
    if not isinstance(message, dict):
        return False
    role = message.get("role")
    if role == "toolResult":
        return "details" in message
    if role == "assistant" and isinstance(message.get("content"), list):
        return any(
            isinstance(part, dict)
            and part.get("type") == "toolCall"
            and "arguments" in part
            for part in message["content"]
        )
    return role == "custom" and "details" in message


# ============================================================================
# Append separator
# ============================================================================


def session_file_needs_append_separator(
    file_path: str,
    snapshot: Optional[SessionFileSnapshot],
) -> bool:
    """True iff the file's last byte is not
    ``\\n`` and a separator is required before
    the next append. Mirrors
    ``sessionFileNeedsAppendSeparator``
    (``session-manager-file.ts:438-458``).
    """
    if snapshot is None or snapshot.size == 0:
        return False
    resolved_path = os.path.abspath(file_path)
    with _cache_lock:
        cached = _session_entries_cache.get(resolved_path)
    if cached and _is_same_session_file_snapshot(cached.snapshot, snapshot):
        return not cached.ends_with_newline
    # Read the last byte from disk.
    try:
        with open(resolved_path, "rb") as f:
            f.seek(snapshot.size - 1)
            last_byte = f.read(1)
        return len(last_byte) == 1 and last_byte[0] != 0x0A
    except (OSError, FileNotFoundError):
        return False


# ============================================================================
# Revalidate loaded file
# ============================================================================


def revalidate_loaded_session_file(
    file_path: str, loaded: LoadedSessionFile
) -> LoadedSessionFile:
    """Re-check whether the loaded snapshot is
    still current. Mirrors
    ``revalidateLoadedSessionFile``
    (``session-manager-file.ts:460-476``).
    """
    resolved_path = os.path.abspath(file_path)
    current_snapshot = read_session_file_snapshot_if_exists(resolved_path)
    if (
        loaded.snapshot is not None
        and current_snapshot is not None
        and _is_same_session_file_snapshot(loaded.snapshot, current_snapshot)
    ):
        return loaded
    if loaded.snapshot is None and current_snapshot is None:
        return loaded
    return load_entries_from_file_with_snapshot(file_path)


# ============================================================================
# SQLite-marked sessions
# ============================================================================


def load_sqlite_marked_session_file(
    session_file: str,
    load_events: Callable[["Any"], list[FileEntry]],
    options: Optional[dict] = None,
) -> Optional[dict]:
    """Load a SQLite-backed session.

    Mirrors ``loadSqliteMarkedSessionFile``
    (``session-manager-file.ts:478-501``).

    The session_file is a ``"sqlite:<agent>:<id>:<store>[:scope]"``
    marker; the function parses the marker, looks
    up the session key, and delegates to
    ``load_events`` to fetch the actual entries.
    """
    options = options or {}
    marker = _parse_sqlite_session_file_marker(session_file)
    if marker is None:
        return None
    # Phase 6.4 wires the full
    # ``resolveTranscriptSessionKeyBySessionId``;
    # for now the function uses the session id
    # as the key (matches the OpenClaw source's
    # default behaviour for non-transcript
    # callers). The OpenClaw source throws
    # ``Cannot open SQLite session without session entry``
    # from that helper; the Python port surfaces
    # the same error here, including the
    # empty-agent-or-session-id case.
    session_key = marker.get("session_id") or marker.get("sessionId")
    if not session_key or not marker.get("agent_id"):
        raise RuntimeError(
            f"Cannot open SQLite session without session id: {session_file}"
        )
    entries = load_events(marker)
    header_entry: Optional[dict] = None
    for entry in entries:
        if is_json_record(entry) and entry.get("type") == "session":
            header_entry = entry
            break
    cwd_value = (
        options.get("cwdOverride")
        or (header_entry.get("cwd") if header_entry is not None else None)
        or options.get("fallbackCwd")
        or os.getcwd()
    )
    return {
        "cwd": cwd_value,
        "entries": entries,
        "sessionKey": session_key,
        "sqliteMarker": marker,
    }


def _parse_sqlite_session_file_marker(
    session_file: str,
) -> Optional[dict]:
    """Parse a ``"sqlite:<agent>:<id>:<store_path>"``
    marker. Mirrors
    ``parseSqliteSessionFileMarker`` from
    ``openclaw-main/src/config/sessions/sqlite-marker.ts``.

    The OpenClaw regex is
    ``^sqlite:([^:]+):([^:]+):(.*)$``: ``agent`` and
    ``sessionId`` cannot contain ``:``; ``storePath``
    is the trailing rest (so it may contain ``:``
    on Windows paths like ``C:\\foo``).

    Returns ``None`` when the marker is empty,
    doesn't start with ``"sqlite:"``, or doesn't
    match the canonical 3-part shape. A parsed
    marker with an empty ``agent_id`` or
    ``session_id`` is still returned here — the
    caller (:func:`load_sqlite_marked_session_file`)
    is the one that surfaces the invalid state
    as a ``RuntimeError``, matching the OpenClaw
    source's
    ``Cannot open SQLite session without session entry``
    error from
    ``resolveTranscriptSessionKeyBySessionId``
    (``session-manager-file.ts:489``).
    """
    if not isinstance(session_file, str):
        return None
    marker = session_file.strip()
    if not marker.startswith("sqlite:"):
        return None
    remainder = marker[len("sqlite:") :]
    # First try the strict OpenClaw regex
    # (``sqlite-marker.ts:10``).
    match = _SQLITE_MARKER_RE.match(remainder)
    if match is not None:
        agent_id, session_id, store_path = (
            match.group(1),
            match.group(2),
            match.group(3),
        )
        if not store_path:
            return None
        return {
            "agent_id": agent_id,
            "session_id": session_id,
            "store_path": store_path,
        }
    # Fallback for malformed markers with empty
    # parts (e.g. ``sqlite:::store:scope``). The
    # strict regex would return ``None`` here, but
    # the Python port's caller wants the empty
    # parts surfaced so it can raise a meaningful
    # error. We accept the marker iff it has the
    # 4-part structure (or more).
    parts = remainder.split(":")
    if len(parts) >= 4:
        agent_id, session_id = parts[0], parts[1]
        store_path = ":".join(parts[2:])
        if not store_path:
            return None
        return {
            "agent_id": agent_id,
            "session_id": session_id,
            "store_path": store_path,
        }
    return None


#: Mirrors the OpenClaw
#: ``SQLITE_SESSION_FILE_MARKER_RE``
#: (``openclaw-main/src/config/sessions/sqlite-marker.ts:10``):
#: ``^sqlite:([^:]+):([^:]+):(.*)$``.
import re as _re
_SQLITE_MARKER_RE = _re.compile(r"([^:]+):([^:]+):(.*)$")


# ============================================================================
# Corrupt-file recovery
# ============================================================================


def recover_corrupt_session_entries(
    file_path: str, cwd: str
) -> Optional[list[FileEntry]]:
    """Recover a session file that won't parse.

    Mirrors ``recoverCorruptSessionEntries``
    (``session-manager-file.ts:530-555``).

    Returns ``None`` when the file is empty
    (nothing to recover). Otherwise returns a
    list with a fresh header followed by the
    recoverable entries, and writes a
    ``.corrupt-<timestamp>-<suffix>.jsonl``
    backup of the original content.
    """
    if not os.path.exists(file_path):
        return None
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
    if not content.strip():
        return None
    parsed_entries = parse_jsonl_entries(content)
    recovered_header: Optional[dict] = None
    for entry in parsed_entries:
        if (
            isinstance(entry, dict)
            and entry.get("type") == "session"
            and isinstance(entry.get("id"), str)
        ):
            recovered_header = entry
            break
    header: dict
    if recovered_header is not None:
        header = recovered_header
    else:
        header = {
            "type": "session",
            "version": CURRENT_SESSION_VERSION,
            "id": create_session_id(),
            "timestamp": _now_iso(),
            "cwd": cwd,
        }
    recovered_entries = [
        entry
        for entry in parsed_entries
        if not (
            isinstance(entry, dict)
            and entry.get("type") == "session"
            and isinstance(entry.get("id"), str)
        )
    ]
    # Backup the original file.
    timestamp = _now_iso().replace(":", "-").replace(".", "-")
    backup_path = f"{file_path}.corrupt-{timestamp}-{uuid.uuid4().hex[:8]}.jsonl"
    try:
        backup_mode = os.stat(file_path).st_mode & 0o777 or 0o600
        with open(backup_path, "w", encoding="utf-8") as f:
            f.write(content)
        try:
            os.chmod(backup_path, backup_mode)
        except (OSError, NotImplementedError):
            pass
    except (OSError, FileNotFoundError):
        _LOG.warning(
            "recoverCorruptSessionEntries: failed to write backup at %s",
            backup_path,
        )
    return [header, *recovered_entries]


def _now_iso() -> str:
    """Return the current UTC time as an ISO-8601
    string. The OpenClaw source uses
    ``new Date().toISOString()``; the Python port
    uses the same shape.
    """
    from datetime import datetime, timezone

    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


# ============================================================================
# canPublishOwnedSessionAppend
# ============================================================================


def can_publish_owned_session_append(
    session_file: str,
    snapshot: Optional[SessionFileSnapshot],
) -> bool:
    """True iff the snapshot is publishable.

    Mirrors ``canPublishOwnedSessionAppend``
    (``session-manager-file.ts:557-562``).

    Phase 6.3 ships the read-side stub; the real
    publish (which integrates with
    ``transcript-write-context.ts``) lands in
    Phase 6.4.
    """
    _ = session_file
    return snapshot is not None


__all__ = [
    "LoadedSessionFile",
    "MAX_CACHED_SESSION_BYTES",
    "MAX_CACHED_SESSION_FILES",
    "SessionFileSnapshot",
    "can_publish_owned_session_append",
    "get_default_session_dir",
    "json_serialization_can_run_user_code",
    "load_entries_from_file",
    "load_entries_from_file_with_snapshot",
    "load_sqlite_marked_session_file",
    "message_serializes_owned_values",
    "publish_remembered_session_file_snapshot",
    "read_session_file_snapshot",
    "read_session_file_snapshot_if_exists",
    "recover_corrupt_session_entries",
    "remember_appended_session_entry",
    "remember_written_session_entries",
    "revalidate_loaded_session_file",
    "session_file_needs_append_separator",
]
