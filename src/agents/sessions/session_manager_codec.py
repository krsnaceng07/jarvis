"""jarvis.agents.sessions.session_manager_codec — session codec.

OpenClaw parity: mirrors
``openclaw-main/src/agents/sessions/session-manager-codec.ts``.

JSONL ↔ typed session-entry codec, plus the schema
migrations (v1 → v2 → v3) and the
``buildSessionContext`` walker that turns a tree
of entries into the linear message list the agent
loop expects.

Parity
======
- ``CURRENT_SESSION_VERSION = 3``
  (matches the OpenClaw ``version.ts`` constant;
  Phase 6.4 ports the explicit version file).
- ``migrateV1ToV2`` / ``migrateV2ToV3``
  (``session-manager-codec.ts:17-63``) — assign
  ``id`` + ``parentId`` to pre-v2 entries; convert
  ``hookMessage`` role to ``custom``.
- ``migrateToCurrentVersion(entries, [by_original_index])``
  (``:65-81``) — run the migrations in order;
  return True when any migration happened.
- ``migrateSessionEntries(entries)`` (``:83-85``) —
  thin wrapper.
- ``parseSessionEntries(content)`` (``:87-89``) —
  the public JSONL parser; delegates to
  :func:`parse_jsonl_entries`.
- ``getLatestCompactionEntry(entries)``
  (``:91-98``) — return the most recent compaction
  or ``None``.
- ``buildSessionContext(entries, leaf_id?, by_id?)``
  (``:100-140``) — walk the tree from ``leaf_id``
  (or the last entry) back to the root, then
  hand the path to the agent-core
  ``buildSessionContext`` to materialise the
  message list. Returns the empty context when
  the leaf is missing / the tree is empty.
- ``parseJsonlEntries(content)`` (``:142-162``) —
  split the JSONL into typed entries, skipping
  malformed lines with a warning.
- ``normalizeLoadedFileEntry(entry)`` (``:164-178``)
  — coerce legacy ``assistant`` / ``toolResult``
  message content to the array shape.
- ``hasReadableSessionHeader(entries)`` (``:180-183``)
  — True iff ``entries[0]`` is a ``SessionHeader``.
- ``isJsonRecord(value)`` (``:185-187``) — type
  guard.
- ``isSessionEntryType(type)`` (private, ``:189-204``)
  — the discriminator switch.
- ``isIndexedSessionEntry(entry)`` (``:206-213``) —
  type guard for ``SessionEntry``.
- ``parseParentLinkedOpaqueEntry(record)``
  (``:215-229``) — type guard for a parent-linked
  opaque entry.
- ``parseOpaqueLeafEntry(record)`` (``:231-261``) —
  type guard for a leaf-control entry.
- ``partitionSessionFileEntries(entries)``
  (``:263-298``) — split the file into the typed
  file-entries + the opaque extras the v1
  schema left behind.

Phase 6.2 — session codec.

Adaptations
-----------
- The OpenClaw source imports
  ``selectSessionTranscriptLeafControlledPath``
  from ``config/sessions/transcript-tree.ts``
  (a Phase 6.3 / 6.4 port). Phase 6.2 ships a
  local stub that returns ``None`` (no leaf
  control) so the linear walk is the only
  supported path. The Phase 6.3 port replaces
  the stub with the real implementation.
- The OpenClaw source uses ``logWarn`` from
  ``logger.js``; the Python port uses the
  standard ``logging`` module via
  :func:`logging.getLogger`.
- ``current_session_version`` is hard-coded to
  ``3`` in Phase 6.2 (the value the v2 → v3
  migration implies). Phase 6.4 imports it from
  the OpenClaw-shaped ``config/sessions/version.py``
  port.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional, TypeGuard

from .session_manager_id import generate_session_entry_id
from .session_manager_types import (
    CompactionEntry,
    FileEntry,
    SessionContext,
    SessionEntry,
    SessionHeader,
    SessionLeafControl,
)


_LOG = logging.getLogger("jarvis.agents.sessions.session_manager_codec")

#: Mirrors the OpenClaw ``CURRENT_SESSION_VERSION``
#: constant (``version.ts``). The session codec
#: runs v1 → v2 → v3 migrations in order; entries
#: with a header at this version are skipped.
CURRENT_SESSION_VERSION = 3


# ============================================================================
# Schema migrations
# ============================================================================


def _migrate_v1_to_v2(
    entries: list[FileEntry],
    entries_by_original_index: Optional[list[Optional[FileEntry]]] = None,
) -> None:
    """Assign ``id`` + ``parentId`` to pre-v2 entries.

    Mirrors ``migrateV1ToV2``
    (``session-manager-codec.ts:17-48``). The v1
    schema did not include the ``id`` /
    ``parentId`` tree-link fields; this migration
    walks the entries in order, generates a
    collision-free 8-char id, and chains them
    into a linear parent pointer chain. For
    compaction entries with a legacy
    ``firstKeptEntryIndex`` field, the index is
    translated to a ``firstKeptEntryId`` pointer.

    The OpenClaw source mutates the entries
    in-place; the Python port does the same so
    the migration is visible to the caller.
    """
    ids: set[str] = set()
    previous_id: Optional[str] = None

    for entry in entries:
        if entry.get("type") == "session":
            entry["version"] = 2
            continue

        new_id = generate_session_entry_id(ids)
        ids.add(new_id)
        entry["id"] = new_id
        entry["parentId"] = previous_id
        previous_id = new_id

        if entry.get("type") == "compaction":
            first_kept_index = entry.get("firstKeptEntryIndex")
            if isinstance(first_kept_index, int):
                target = None
                if entries_by_original_index is not None:
                    target = entries_by_original_index[first_kept_index]
                if target is None and first_kept_index < len(entries):
                    target = entries[first_kept_index]
                if target is not None and target.get("type") != "session":
                    entry["firstKeptEntryId"] = target.get("id")
                # Remove the legacy index pointer.
                if "firstKeptEntryIndex" in entry:
                    del entry["firstKeptEntryIndex"]


def _migrate_v2_to_v3(entries: list[FileEntry]) -> None:
    """Rename ``hookMessage`` role to ``custom``.

    Mirrors ``migrateV2ToV3``
    (``session-manager-codec.ts:50-63``). The v2
    schema used a ``hookMessage`` message role
    that the v3 schema renamed to ``custom``.
    The migration only touches the ``role`` field
    on each message — the rest of the entry is
    left alone.
    """
    for entry in entries:
        if entry.get("type") == "session":
            entry["version"] = 3
            continue
        if entry.get("type") != "message":
            continue
        message = entry.get("message")
        if not isinstance(message, dict):
            continue
        if message.get("role") == "hookMessage":
            message["role"] = "custom"


def migrate_to_current_version(
    entries: list[FileEntry],
    entries_by_original_index: Optional[list[Optional[FileEntry]]] = None,
) -> bool:
    """Run every schema migration in order. Mirrors
    ``migrateToCurrentVersion``
    (``session-manager-codec.ts:65-81``).

    Returns ``True`` iff at least one migration
    was applied; the caller persists the
    migrated entries to disk on a True return.
    """
    header = next(
        (entry for entry in entries if entry.get("type") == "session"),
        None,
    )
    version = header.get("version", 1) if isinstance(header, dict) else 1
    if version >= CURRENT_SESSION_VERSION:
        return False
    if version < 2:
        _migrate_v1_to_v2(entries, entries_by_original_index)
    if version < 3:
        _migrate_v2_to_v3(entries)
    return True


def migrate_session_entries(entries: list[FileEntry]) -> None:
    """Convenience wrapper around
    :func:`migrate_to_current_version`. Mirrors
    ``migrateSessionEntries``
    (``session-manager-codec.ts:83-85``)."""
    migrate_to_current_version(entries)


# ============================================================================
# Latest compaction lookup
# ============================================================================


def get_latest_compaction_entry(
    entries: list[SessionEntry],
) -> Optional[CompactionEntry]:
    """Return the most recent compaction entry, or
    ``None``. Mirrors ``getLatestCompactionEntry``
    (``session-manager-codec.ts:91-98``). Walks
    the entries in reverse (the OpenClaw source
    uses ``toReversed()``; the Python port uses
    a reversed iterator).
    """
    for entry in reversed(entries):
        if entry.get("type") == "compaction":
            return entry  # type: ignore[return-value]
    return None


# ============================================================================
# buildSessionContext
# ============================================================================


def _select_leaf_controlled_path(
    entries: list[SessionEntry],
) -> Optional[list[SessionEntry]]:
    """Apply leaf-control pruning to the entries.

    Mirrors the ``selectSessionTranscriptLeafControlledPath``
    helper imported by ``buildSessionContext``
    from ``config/sessions/transcript-tree.ts``.
    Phase 6.2 ships a stub that returns
    ``None`` (no leaf control) so the linear
    walk is the only supported path. The
    Phase 6.3 port replaces the stub with the
    full implementation.
    """
    return None


def build_session_context(
    entries: list[SessionEntry],
    leaf_id: Optional[str] = None,
    by_id_input: Optional[dict] = None,
) -> SessionContext:
    """Build a session context from a list of
    tree-linked entries.

    Mirrors ``buildSessionContext``
    (``session-manager-codec.ts:100-140``).

    The OpenClaw source delegates the final
    path-to-context step to the agent-core
    ``buildSessionContext`` (so the message-list
    projection lives in one place). The Python
    port implements the same projection locally
    on the dict shape the codec already produces;
    the agent-runtime's ``buildSessionContext``
    is reserved for the typed SessionTreeEntry
    flow (Phase 6.4 ports the full
    dict → typed conversion).

    Parameters
    ----------
    entries : list[SessionEntry]
        The flat list of file entries (in insertion
        order). The function builds the ``by_id``
        map + walks the parent chain.
    leaf_id : str | None
        Optional explicit leaf id. ``None``
        (default) auto-selects via the leaf-
        controlled path; ``""`` / falsy disables
        the leaf filter; an explicit id is used
        directly.
    by_id_input : dict | None
        Optional pre-built ``id -> entry`` map.
        Pass-through for callers that already
        maintain the index.

    Returns
    -------
    SessionContext
        The empty context when the entries are
        empty or the leaf is missing; otherwise a
        ``SessionContext`` with the messages +
        thinking level + model materialised from
        the leaf-to-root walk.
    """
    context_entries = entries
    context_by_id = by_id_input

    # When ``leaf_id`` is ``None`` (the default),
    # the OpenClaw source consults the
    # leaf-controlled path resolver. Phase 6.2
    # ships a stub that returns ``None`` (no
    # leaf control) so the linear path is used
    # unchanged.
    if leaf_id is None:
        selected = _select_leaf_controlled_path(entries)
        if selected is not None:
            context_entries = selected
            context_by_id = None

    by_id: dict = context_by_id if context_by_id is not None else {}
    if not by_id:
        by_id = {}
        for entry in context_entries:
            entry_id = entry.get("id") if isinstance(entry, dict) else None
            if entry_id is not None:
                by_id[entry_id] = entry

    # ``leaf_id is None`` means "use the last
    # entry" (auto-select). ``leaf_id is ""`` or
    # any other falsy short-circuits the walk to
    # the empty context — matches the OpenClaw
    # ``if (leafId === null) return { ...empty }``
    # short-circuit (``session-manager-codec.ts:123-125``).
    if leaf_id is not None and not leaf_id:
        return SessionContext(messages=[], thinking_level="off", model=None)
    if leaf_id is None:
        leaf = context_entries[-1] if context_entries else None
    else:
        leaf = by_id.get(leaf_id) or (
            context_entries[-1] if context_entries else None
        )
    if not leaf:
        return SessionContext(messages=[], thinking_level="off", model=None)

    # Walk the parent chain from the leaf back to
    # the root.
    path: list[SessionEntry] = []
    current: Optional[SessionEntry] = leaf  # type: ignore[assignment]
    while current is not None:
        path.append(current)
        current_parent_id = (
            current.get("parentId") if isinstance(current, dict) else None
        )
        current = by_id.get(current_parent_id) if current_parent_id else None
    path.reverse()

    # Project the path to a ``SessionContext``.
    # The projection mirrors the OpenClaw core
    # ``buildSessionContext`` algorithm:
    # 1. The last ``thinking_level_change`` /
    #    ``model_change`` entry wins.
    # 2. The messages are the ``message`` field of
    #    each entry in root-to-leaf order,
    #    skipping entries whose type is
    #    session-bookkeeping (``label``,
    #    ``session_info``, ``custom``,
    #    ``thinking_level_change``,
    #    ``model_change``, ``compaction``,
    #    ``branch_summary`` with empty summary).
    thinking_level = "off"
    model: Optional[dict] = None
    messages: list = []
    for entry in path:
        if not isinstance(entry, dict):
            continue
        entry_type = entry.get("type")
        if entry_type == "thinking_level_change":
            thinking_level = entry.get("thinkingLevel", "off")
        elif entry_type == "model_change":
            provider = entry.get("provider")
            model_id = entry.get("modelId")
            if isinstance(provider, str) and isinstance(model_id, str):
                model = {"provider": provider, "modelId": model_id}
        elif entry_type == "message":
            message = entry.get("message")
            if isinstance(message, dict):
                # Auto-detect the model from the last
                # assistant message (matches the
                # OpenClaw core logic).
                if (
                    message.get("role") == "assistant"
                    and model is None
                ):
                    provider = message.get("provider")
                    model_id = message.get("model")
                    if isinstance(provider, str) and isinstance(
                        model_id, str
                    ):
                        model = {
                            "provider": provider,
                            "modelId": model_id,
                        }
                messages.append(message)
        elif entry_type == "custom_message":
            content = entry.get("content")
            details = entry.get("details")
            custom_type = entry.get("customType", "")
            display = bool(entry.get("display", False))
            timestamp = entry.get("timestamp")
            if isinstance(content, (str, list)) and isinstance(
                timestamp, str
            ):
                # Minimal ``CustomMessage`` projection
                # so callers see a uniform
                # ``AgentMessage`` list. The full
                # conversion uses
                # ``jarvis_agent.messages.create_custom_message``
                # in Phase 6.4.
                messages.append(
                    {
                        "role": "custom",
                        "customType": custom_type,
                        "content": content,
                        "display": display,
                        "details": details,
                        "timestamp": timestamp,
                    }
                )
        elif entry_type == "branch_summary":
            summary = entry.get("summary")
            from_id = entry.get("fromId", "")
            timestamp = entry.get("timestamp")
            if (
                isinstance(summary, str)
                and summary
                and isinstance(timestamp, str)
            ):
                messages.append(
                    {
                        "role": "branchSummary",
                        "summary": summary,
                        "fromId": from_id,
                        "timestamp": timestamp,
                    }
                )

    return SessionContext(
        messages=messages,
        thinking_level=thinking_level,
        model=model,
    )


# ============================================================================
# JSONL parsing
# ============================================================================


def parse_jsonl_entries(content: str) -> list[FileEntry]:
    """Parse a JSONL session file into typed
    entries. Mirrors ``parseJsonlEntries``
    (``session-manager-codec.ts:142-162``).

    Skips blank lines + malformed lines (with a
    warning log) and runs :func:`normalize_loaded_file_entry`
    on each parsed entry.
    """
    entries: list[FileEntry] = []
    skipped = 0
    # ``content.strip()`` matches the OpenClaw
    # ``content.trim()``; an empty content yields
    # no entries (no warning either).
    for line in content.strip().split("\n"):
        if not line.strip():
            continue
        try:
            parsed = json.loads(line)
        except (ValueError, TypeError):
            skipped += 1
            continue
        entries.append(normalize_loaded_file_entry(parsed))
    if skipped > 0:
        _LOG.warning(
            "parseJsonlEntries: skipped %d malformed JSONL line(s); "
            "%d valid entries were loaded",
            skipped,
            len(entries),
        )
    return entries


def parse_session_entries(content: str) -> list[FileEntry]:
    """Public alias for :func:`parse_jsonl_entries`.

    Mirrors ``parseSessionEntries``
    (``session-manager-codec.ts:87-89``).
    """
    return parse_jsonl_entries(content)


# ============================================================================
# Loaded-entry normalization
# ============================================================================


def normalize_loaded_file_entry(entry: FileEntry) -> FileEntry:
    """Coerce legacy ``assistant`` / ``toolResult``
    message content to the array shape.

    Mirrors ``normalizeLoadedFileEntry``
    (``session-manager-codec.ts:164-178``).

    The OpenClaw source mutates the entry
    in-place when the message content is a
    string; the Python port preserves the same
    in-place mutation behaviour (the entry
    dict is shared with the caller, so an
    out-of-place copy would surprise them).
    """
    if not _is_json_record(entry) or entry.get("type") != "message":
        return entry
    message = entry.get("message")
    if not _is_json_record(message):
        return entry

    role = message.get("role")
    content = message.get("content")
    if role in ("assistant", "toolResult") and isinstance(content, str):
        message["content"] = [{"type": "text", "text": content}]
    elif role == "toolResult" and _is_json_record(content):
        message["content"] = [content]
    return entry


# ============================================================================
# Header check + type guards
# ============================================================================


def has_readable_session_header(entries: list[FileEntry]) -> bool:
    """True iff ``entries[0]`` is a session header
    with a string ``id``. Mirrors
    ``hasReadableSessionHeader``
    (``session-manager-codec.ts:180-183``).
    """
    if not entries:
        return False
    header = entries[0]
    return (
        isinstance(header, dict)
        and header.get("type") == "session"
        and isinstance(header.get("id"), str)
    )


def is_json_record(value: object) -> TypeGuard[dict]:
    """Type guard: True iff ``value`` is a JSON
    object (not array, not null). Mirrors
    ``isJsonRecord``
    (``session-manager-codec.ts:185-187``).
    """
    return isinstance(value, dict)


#: Discriminator switch for the ``type`` field.
#: Mirrors the private ``isSessionEntryType``
#: (``session-manager-codec.ts:189-204``). The
#: Python port exposes the same set as a frozenset
#: so callers can test membership directly.
_SESSION_ENTRY_TYPES: frozenset[str] = frozenset(
    {
        "message",
        "thinking_level_change",
        "model_change",
        "compaction",
        "branch_summary",
        "custom",
        "custom_message",
        "label",
        "session_info",
    }
)


def is_session_entry_type(type_value: object) -> bool:
    """True iff ``type_value`` is a known session
    entry type. Mirrors the private
    ``isSessionEntryType``
    (``session-manager-codec.ts:189-204``).
    """
    return isinstance(type_value, str) and type_value in _SESSION_ENTRY_TYPES


def is_indexed_session_entry(entry: object) -> TypeGuard[SessionEntry]:
    """Type guard for ``SessionEntry``. Mirrors
    ``isIndexedSessionEntry``
    (``session-manager-codec.ts:206-213``).
    """
    return (
        _is_json_record(entry)
        and is_session_entry_type(entry.get("type"))
        and isinstance(entry.get("id"), str)
        and len(entry.get("id", "")) > 0
    )


# Local alias for the underscore-prefixed import.
_is_json_record = is_json_record


# ============================================================================
# Opaque-entry parsers
# ============================================================================


def parse_parent_linked_opaque_entry(
    record: object,
) -> Optional[dict]:
    """Type guard for a parent-linked opaque
    entry. Mirrors ``parseParentLinkedOpaqueEntry``
    (``session-manager-codec.ts:215-229``).

    Returns the ``{id, parentId}`` projection, or
    ``None`` if the record does not match the
    shape.
    """
    if not _is_json_record(record):
        return None
    if record.get("type") == "session" or record.get("type") == "leaf":
        return None
    if not isinstance(record.get("id"), str) or len(record.get("id", "")) == 0:
        return None
    parent_id = record.get("parentId")
    if parent_id is not None and not isinstance(parent_id, str):
        return None
    return {"id": record.get("id"), "parentId": parent_id}


def parse_opaque_leaf_entry(record: object) -> Optional[dict]:
    """Type guard for a leaf-control opaque entry.

    Mirrors ``parseOpaqueLeafEntry``
    (``session-manager-codec.ts:231-261``).
    Returns the projection dict (with
    ``appendParentId`` + ``appendMode`` only when
    set), or ``None``.
    """
    if not _is_json_record(record):
        return None
    if record.get("type") != "leaf":
        return None
    if not isinstance(record.get("id"), str) or len(record.get("id", "")) == 0:
        return None
    parent_id = record.get("parentId")
    if parent_id is not None and not isinstance(parent_id, str):
        return None
    target_id = record.get("targetId")
    if target_id is not None and not isinstance(target_id, str):
        return None
    append_parent_id = record.get("appendParentId")
    if (
        append_parent_id is not None
        and append_parent_id is not False  # allow literal ``False``
        and not isinstance(append_parent_id, str)
    ):
        return None
    append_mode = record.get("appendMode")
    if append_mode is not None and append_mode != "side":
        return None

    result: dict[str, Any] = {
        "id": record.get("id"),
        "parentId": parent_id,
        "targetId": target_id,
    }
    if append_parent_id is not None:
        result["appendParentId"] = append_parent_id
    if append_mode == "side":
        result["appendMode"] = append_mode
    return result


# ============================================================================
# partitionSessionFileEntries
# ============================================================================


def partition_session_file_entries(
    entries: list[FileEntry],
) -> dict:
    """Split a flat list of file entries into the
    typed ``FileEntry`` rows + the opaque
    extras. Mirrors ``partitionSessionFileEntries``
    (``session-manager-codec.ts:263-298``).

    Returns
    -------
    dict
        ``{"fileEntries": [...], "opaqueEntries":
        [{"index", "record"}], "fileEntriesByOriginalIndex":
        [...]}``. The ``opaqueEntries`` are the
        non-file rows preserved as opaque
        ``record`` blobs; the ``fileEntriesByOriginalIndex``
        is a sparse list with the file-entries
        placed at their original positions (None
        for the opaque slots).
    """
    file_entries: list[FileEntry] = []
    opaque_entries: list[dict] = []
    file_entries_by_original_index: list[Optional[FileEntry]] = []

    header: Optional[SessionHeader] = None
    for entry in entries:
        if (
            _is_json_record(entry)
            and entry.get("type") == "session"
            and isinstance(entry.get("id"), str)
        ):
            header = entry  # type: ignore[assignment]
            break
    accepts_legacy_entries = (
        header.get("version", 1) < 2 if isinstance(header, dict) else True
    )

    has_header = False
    for original_index, entry in enumerate(entries):
        if (
            not has_header
            and _is_json_record(entry)
            and entry.get("type") == "session"
            and isinstance(entry.get("id"), str)
        ):
            file_entries.append(entry)  # type: ignore[arg-type]
            file_entries_by_original_index.append(entry)
            has_header = True
            continue
        if is_indexed_session_entry(entry) or (
            accepts_legacy_entries
            and _is_json_record(entry)
            and is_session_entry_type(entry.get("type"))
        ):
            file_entries.append(entry)
            file_entries_by_original_index.append(entry)
            continue
        opaque_entries.append({"index": len(file_entries), "record": entry})

    return {
        "fileEntries": file_entries,
        "opaqueEntries": opaque_entries,
        "fileEntriesByOriginalIndex": file_entries_by_original_index,
    }


__all__ = [
    "CURRENT_SESSION_VERSION",
    "build_session_context",
    "get_latest_compaction_entry",
    "has_readable_session_header",
    "is_indexed_session_entry",
    "is_json_record",
    "is_session_entry_type",
    "migrate_session_entries",
    "migrate_to_current_version",
    "normalize_loaded_file_entry",
    "parse_jsonl_entries",
    "parse_opaque_leaf_entry",
    "parse_parent_linked_opaque_entry",
    "parse_session_entries",
    "partition_session_file_entries",
]
