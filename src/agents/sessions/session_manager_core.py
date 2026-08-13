"""jarvis.agents.sessions.session_manager_core — session manager core.

OpenClaw parity: mirrors
``openclaw-main/src/agents/sessions/session-manager-core.ts``.

The :class:`SessionManagerCore` is the base of
the session-manager class hierarchy
(``Core`` → ``Persistence`` → ``Entries`` →
``Branching``). It owns the file-load + index-
build + replace-persisted-transcript lifecycle.

Phase 6.4a — session core (base class).

Adaptations
-----------
- The OpenClaw source mutates a ``Map`` for
  ``byId`` / ``opaqueParentsById`` /
  ``logicalParentsById`` / etc. The Python
  port uses a ``dict`` (insertion-ordered) for
  the same shape, plus a plain ``set`` for
  ``invalidLeafControlIds``.
- The OpenClaw source uses Node ``fs`` sync
  APIs. The Python port uses :mod:`os` +
  :mod:`json` (the file helpers in
  :mod:`jarvis.agents.sessions.session_manager_file`
  + :mod:`jarvis.agents.sessions.session_manager_codec`
  already exist from Phase 6.2 + 6.3).
- The OpenClaw source's ``replaceTranscriptEventsSync``
  / ``appendTranscriptEventSync`` are SQLite
  helpers from
  ``config/sessions/session-accessor.ts``. The
  Python port ships the file-only path for now;
  the SQLite path is a stub for Phase 6.5 (the
  ``session_manager_facade`` wires the full
  ``createAgentSession`` + the transcript DB).
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from .session_manager_codec import (
    CURRENT_SESSION_VERSION,
    has_readable_session_header,
    is_indexed_session_entry,
    is_json_record,
    migrate_to_current_version,
    parse_opaque_leaf_entry,
    parse_parent_linked_opaque_entry,
    partition_session_file_entries,
)
from .session_manager_file import (
    LoadedSessionFile,
    SessionFileSnapshot,
    load_entries_from_file_with_snapshot,
    load_sqlite_marked_session_file,
    publish_remembered_session_file_snapshot,
    recover_corrupt_session_entries,
    remember_written_session_entries,
)
from .session_manager_id import create_session_id, generate_session_entry_id
from .session_manager_types import (
    FileEntry,
    NewSessionOptions,
    PreservedOpaqueFileEntry,
    SessionEntry,
    SessionHeader,
    SessionLeafControl,
)


_LOG = logging.getLogger("jarvis.agents.sessions.session_manager_core")


# ============================================================================
# SqliteSessionManagerPersistence
# ============================================================================


#: Mirrors ``SqliteSessionManagerPersistence``
#: (``session-manager-core.ts:41-43``). The
#: Python port uses snake_case keys. Phase 6.5
#: wires the full transcript DB read/write
#: helpers.
SqliteSessionManagerPersistence = dict


# ============================================================================
# SessionManagerCore
# ============================================================================


def _now_iso() -> str:
    """Return the current UTC time as an ISO-8601
    string. The OpenClaw source uses
    ``new Date().toISOString()``; the Python port
    uses the same shape.
    """
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


class SessionManagerCore:
    """Base class for the session-manager
    hierarchy. Mirrors ``SessionManagerCore``
    (``session-manager-core.ts:45-608``).

    The Python port ships the file-backed
    lifecycle (load, save, index, rewrite) +
    the leaf-control helpers. The
    SQLite-backed persistence path is a stub
    for Phase 6.5.
    """

    def __init__(
        self,
        cwd: str,
        session_dir: str,
        session_file: Optional[str],
        persist: bool,
        loaded_session_file: Optional[LoadedSessionFile] = None,
        sqlite_persistence: Optional[SqliteSessionManagerPersistence] = None,
    ) -> None:
        self.cwd = cwd
        self.session_dir = session_dir
        self.should_persist = persist
        self.sqlite_persistence = sqlite_persistence
        if persist and session_dir and not os.path.isdir(session_dir):
            os.makedirs(session_dir, exist_ok=True)

        # Mutable state — mirrors the OpenClaw
        # source's ``protected`` fields. The Python
        # port does not enforce protected access
        # (subclasses in the same module + tests
        # are the only callers).
        self.session_id: str = ""
        self.session_file: Optional[str] = session_file
        self.flushed: bool = False
        self.file_entries: list[FileEntry] = []
        self.opaque_file_entries: list[PreservedOpaqueFileEntry] = []
        self.by_id: dict[str, SessionEntry] = {}
        self.opaque_parents_by_id: dict[str, Optional[str]] = {}
        self.logical_parents_by_id: dict[str, Optional[str]] = {}
        self.invalid_leaf_control_ids: set[str] = set()
        self.labels_by_id: dict[str, str] = {}
        self.label_timestamps_by_id: dict[str, str] = {}
        self.leaf_id: Optional[str] = None
        self.append_parent_id: Optional[str] = None
        self.prompt_released_side_branch_parent_id: Optional[str] = None
        self.recovered_corrupt_header: bool = False
        self.session_file_snapshot: Optional[SessionFileSnapshot] = None

        if session_file:
            if sqlite_persistence:
                self.set_loaded_sqlite_session_file(
                    session_file,
                    loaded_session_file
                    if loaded_session_file is not None
                    else LoadedSessionFile(entries=[], snapshot=None),
                )
            else:
                self.set_loaded_session_file(
                    session_file,
                    loaded_session_file
                    if loaded_session_file is not None
                    else load_entries_from_file_with_snapshot(session_file),
                )
        else:
            self.new_session()

    # ------------------------------------------------------------------
    # setSessionFile
    # ------------------------------------------------------------------

    def set_session_file(self, session_file: str) -> None:
        """Load a session from a file path.

        Mirrors ``setSessionFile``
        (``session-manager-core.ts:100-120``).
        """
        sqlite_loaded = load_sqlite_marked_session_file(
            session_file,
            load_events=self._sqlite_load_events,
            options={"fallbackCwd": self.cwd},
        )
        if sqlite_loaded:
            self.cwd = sqlite_loaded["cwd"]
            self.sqlite_persistence = {
                **sqlite_loaded["sqliteMarker"],
                "session_key": sqlite_loaded["sessionKey"],
            }
            self.set_loaded_sqlite_session_file(
                session_file,
                LoadedSessionFile(
                    entries=sqlite_loaded["entries"], snapshot=None
                ),
            )
            return
        self.sqlite_persistence = None
        self.set_loaded_session_file(
            session_file, load_entries_from_file_with_snapshot(session_file)
        )

    def _sqlite_load_events(self, marker: dict) -> list[FileEntry]:
        from jarvis_state_core import load_agent_session_entries, open_agent_database

        handle = open_agent_database(
            {
                "agent_id": str(marker.get("agent_id", "")),
                "path": str(marker.get("store_path", "")),
            }
        )
        return load_agent_session_entries(handle, str(marker.get("session_id", "")))

    # ------------------------------------------------------------------
    # setLoadedSessionFile
    # ------------------------------------------------------------------

    def set_loaded_session_file(
        self, session_file: str, loaded: LoadedSessionFile
    ) -> None:
        """Load a JSONL session file. Mirrors
        ``setLoadedSessionFile``
        (``session-manager-core.ts:122-172``)."""
        self.session_file = os.path.abspath(session_file)
        self.session_file_snapshot = None
        self.recovered_corrupt_header = False
        if not os.path.exists(self.session_file):
            explicit_path = self.session_file
            self.new_session()
            self.session_file = explicit_path
            return

        partitioned = partition_session_file_entries(loaded.entries)
        self.file_entries = partitioned["fileEntries"]
        self.opaque_file_entries = partitioned["opaqueEntries"]
        self.session_file_snapshot = loaded.snapshot
        if not self.file_entries:
            recovered_entries = recover_corrupt_session_entries(
                self.session_file, self.cwd
            )
            if recovered_entries and has_readable_session_header(recovered_entries):
                recovered = partition_session_file_entries(recovered_entries)
                self.file_entries = recovered["fileEntries"]
                self.opaque_file_entries = recovered["opaqueEntries"]
                header = next(
                    (
                        entry
                        for entry in self.file_entries
                        if isinstance(entry, dict) and entry.get("type") == "session"
                    ),
                    None,
                )
                self.session_id = (
                    header.get("id")
                    if isinstance(header, dict) and isinstance(header.get("id"), str)
                    else create_session_id()
                )
                migrate_to_current_version(
                    self.file_entries, recovered["fileEntriesByOriginalIndex"]
                )
                self.build_index()
                self.replace_persisted_transcript()
                self.recovered_corrupt_header = True
                self.flushed = True
                return

            explicit_path = self.session_file
            self.new_session()
            self.session_file = explicit_path
            self.replace_persisted_transcript()
            self.flushed = True
            return

        header = next(
            (
                entry
                for entry in self.file_entries
                if isinstance(entry, dict) and entry.get("type") == "session"
            ),
            None,
        )
        self.session_id = (
            header.get("id")
            if isinstance(header, dict) and isinstance(header.get("id"), str)
            else create_session_id()
        )
        migrated = migrate_to_current_version(
            self.file_entries, partitioned["fileEntriesByOriginalIndex"]
        )
        self.build_index()
        if migrated:
            self.replace_persisted_transcript()
        self.flushed = True

    # ------------------------------------------------------------------
    # setLoadedSqliteSessionFile
    # ------------------------------------------------------------------

    def set_loaded_sqlite_session_file(
        self, session_file: str, loaded: LoadedSessionFile
    ) -> None:
        """Load a SQLite-backed session. Mirrors
        ``setLoadedSqliteSessionFile``
        (``session-manager-core.ts:174-191``)."""
        self.session_file = session_file
        self.session_file_snapshot = None
        self.recovered_corrupt_header = False
        partitioned = partition_session_file_entries(loaded.entries)
        if not partitioned["fileEntries"]:
            sqlite_session_id = (
                self.sqlite_persistence.get("session_id")
                if self.sqlite_persistence
                else None
            )
            self.new_session(NewSessionOptions(id=sqlite_session_id))
            self.session_file = session_file
            return
        self.file_entries = partitioned["fileEntries"]
        self.opaque_file_entries = partitioned["opaqueEntries"]
        header = next(
            (
                entry
                for entry in self.file_entries
                if isinstance(entry, dict) and entry.get("type") == "session"
            ),
            None,
        )
        self.session_id = (
            header.get("id")
            if isinstance(header, dict) and isinstance(header.get("id"), str)
            else (
                self.sqlite_persistence.get("session_id")
                if self.sqlite_persistence
                else None
            )
            or create_session_id()
        )
        migrate_to_current_version(
            self.file_entries, partitioned["fileEntriesByOriginalIndex"]
        )
        self.build_index()
        self.flushed = True

    # ------------------------------------------------------------------
    # newSession
    # ------------------------------------------------------------------

    def new_session(self, options: Optional[NewSessionOptions] = None) -> Optional[str]:
        """Start a new session. Mirrors ``newSession``
        (``session-manager-core.ts:193-224``).

        When ``self.should_persist`` is True and
        ``session_dir`` is set, a new file path is
        generated as
        ``<session_dir>/<iso_ts>_<session_id>.jsonl``.
        Returns the new ``sessionFile`` path (or
        ``None`` when not persisting).
        """
        options = options or NewSessionOptions()
        self.recovered_corrupt_header = False
        self.session_file_snapshot = None
        self.session_id = options.id or create_session_id()
        timestamp = _now_iso()
        header: SessionHeader = {
            "type": "session",
            "version": CURRENT_SESSION_VERSION,
            "id": self.session_id,
            "timestamp": timestamp,
            "cwd": self.cwd,
        }
        if options.parent_session is not None:
            header["parentSession"] = options.parent_session
        self.file_entries = [header]
        self.opaque_file_entries = []
        self.by_id.clear()
        self.opaque_parents_by_id.clear()
        self.logical_parents_by_id.clear()
        self.invalid_leaf_control_ids.clear()
        self.labels_by_id.clear()
        self.label_timestamps_by_id.clear()
        self.leaf_id = None
        self.append_parent_id = None
        self.prompt_released_side_branch_parent_id = None
        self.flushed = False

        if self.should_persist:
            if self.sqlite_persistence:
                agent_id = self.sqlite_persistence.get("agent_id", "")
                store_path = self.sqlite_persistence.get("store_path", "")
                self.session_file = f"sqlite:{agent_id}:{self.session_id}:{store_path}"
                persist_sqlite_record = getattr(self, "_persist_sqlite_record", None)
                if callable(persist_sqlite_record):
                    persist_sqlite_record(header)
            else:
                file_timestamp = timestamp.replace(":", "-").replace(".", "-")
                self.session_file = os.path.join(
                    self.get_session_dir(),
                    f"{file_timestamp}_{self.session_id}.jsonl",
                )
        return self.session_file

    # ------------------------------------------------------------------
    # resolveOpaqueLeafTargetId / AppendParentId / LeafControl
    # ------------------------------------------------------------------

    def resolve_opaque_leaf_target_id(self, target_id: Optional[str]) -> Optional[str]:
        """Resolve an opaque leaf target id. Mirrors
        ``resolveOpaqueLeafTargetId``
        (``session-manager-core.ts:226-231``)."""
        if target_id is None or target_id in self.by_id:
            return target_id
        return self.resolve_canonical_parent_id(target_id)

    def resolve_opaque_append_parent_id(self, parent_id: Optional[str]) -> Optional[str]:
        """Resolve an opaque leaf append-parent id. Mirrors
        ``resolveOpaqueAppendParentId``
        (``session-manager-core.ts:233-238``)."""
        if (
            parent_id is None
            or parent_id in self.by_id
            or parent_id in self.opaque_parents_by_id
        ):
            return parent_id
        return self.resolve_canonical_parent_id(parent_id)

    def resolve_opaque_leaf_control(
        self, leaf_entry: Optional[dict]
    ) -> Optional[dict]:
        """Resolve an opaque leaf control. Mirrors
        ``resolveOpaqueLeafControl``
        (``session-manager-core.ts:240-265``)."""
        if not leaf_entry:
            return None

        def is_known_reference(id_: Optional[str]) -> bool:
            if id_ is None:
                return True
            if id_ in self.by_id:
                return True
            if id_ in self.opaque_parents_by_id and id_ not in self.invalid_leaf_control_ids:
                return True
            return False

        if not is_known_reference(leaf_entry.get("targetId")) or (
            leaf_entry.get("appendParentId") is not None
            and not is_known_reference(leaf_entry.get("appendParentId"))
        ):
            return None
        leaf_id = self.resolve_opaque_leaf_target_id(leaf_entry.get("targetId"))
        return {
            "leafId": leaf_id,
            "appendParentId": (
                leaf_entry.get("appendParentId")
                if leaf_entry.get("appendParentId") is not None
                else leaf_id
            )
            if leaf_entry.get("appendParentId") is not None
            else leaf_id,
            **(
                {"appendMode": leaf_entry.get("appendMode")}
                if leaf_entry.get("appendMode")
                else {}
            ),
        }

    # ------------------------------------------------------------------
    # buildIndex
    # ------------------------------------------------------------------

    def build_index(self) -> None:
        """Rebuild the entry indexes. Mirrors
        ``buildIndex``
        (``session-manager-core.ts:267-341``)."""
        self.by_id.clear()
        self.opaque_parents_by_id.clear()
        self.logical_parents_by_id.clear()
        self.invalid_leaf_control_ids.clear()
        self.labels_by_id.clear()
        self.label_timestamps_by_id.clear()
        self.leaf_id = None
        self.append_parent_id = None
        self.prompt_released_side_branch_parent_id = None
        opaque_index = 0
        for index in range(len(self.file_entries) + 1):
            while (
                opaque_index < len(self.opaque_file_entries)
                and self.opaque_file_entries[opaque_index].get("index") == index
            ):
                opaque_record = self.opaque_file_entries[opaque_index].get("record")
                leaf_entry = parse_opaque_leaf_entry(opaque_record)
                if leaf_entry is not None:
                    leaf_state = self.resolve_opaque_leaf_control(leaf_entry)
                    if not leaf_state:
                        self.invalid_leaf_control_ids.add(leaf_entry["id"])
                        self.opaque_parents_by_id[leaf_entry["id"]] = (
                            self.resolve_opaque_append_parent_id(leaf_entry.get("parentId"))
                        )
                        opaque_index += 1
                        continue
                    self.opaque_parents_by_id[leaf_entry["id"]] = leaf_state["leafId"]
                    self.leaf_id = leaf_state["leafId"]
                    self.append_parent_id = leaf_state["appendParentId"]
                    if leaf_state.get("appendMode") == "side":
                        self.prompt_released_side_branch_parent_id = leaf_state[
                            "appendParentId"
                        ]
                    else:
                        self.prompt_released_side_branch_parent_id = None
                    opaque_index += 1
                    continue
                link = parse_parent_linked_opaque_entry(opaque_record)
                if link is not None:
                    self.opaque_parents_by_id[link["id"]] = link["parentId"]
                    self.append_parent_id = link["id"]
                    if self.prompt_released_side_branch_parent_id is not None:
                        self.prompt_released_side_branch_parent_id = link["id"]
                opaque_index += 1
            entry = self.file_entries[index] if index < len(self.file_entries) else None
            if entry is None or not is_indexed_session_entry(entry):
                continue
            has_parent_id = "parentId" in entry
            parent_id_matches = entry.get("parentId") == self.append_parent_id
            leaf_id_differs = self.leaf_id != self.append_parent_id
            if not has_parent_id or (
                parent_id_matches is False
                and leaf_id_differs
                and not _is_session_transcript_side_append_entry(entry)
            ):
                # When the entry's stored parentId
                # matches the current append parent
                # AND the leaf is not the same as the
                # append parent (i.e. side-branch
                # implicit parent resolution), the
                # OpenClaw source records the leaf
                # as the *logical* parent. The
                # Python port mirrors this with the
                # same condition.
                self.logical_parents_by_id[entry["id"]] = self.leaf_id
            elif not has_parent_id or (
                entry.get("parentId") == self.append_parent_id
                and self.leaf_id != self.append_parent_id
                and not _is_session_transcript_side_append_entry(entry)
            ):
                self.logical_parents_by_id[entry["id"]] = self.leaf_id
            self.by_id[entry["id"]] = entry
            self.append_parent_id = entry["id"]
            if _is_session_transcript_side_append_entry(entry):
                self.prompt_released_side_branch_parent_id = entry["id"]
            else:
                self.leaf_id = entry["id"]
                self.prompt_released_side_branch_parent_id = None
            if entry.get("type") == "label":
                target_id = entry.get("targetId")
                if entry.get("label"):
                    if isinstance(target_id, str):
                        self.labels_by_id[target_id] = entry["label"]
                        self.label_timestamps_by_id[target_id] = entry.get(
                            "timestamp", ""
                        )
                else:
                    if isinstance(target_id, str):
                        self.labels_by_id.pop(target_id, None)
                        self.label_timestamps_by_id.pop(target_id, None)

    # ------------------------------------------------------------------
    # resolveCanonicalParentId
    # ------------------------------------------------------------------

    def resolve_canonical_parent_id(self, parent_id: Optional[str]) -> Optional[str]:
        """Resolve a parent id through the opaque
        chain. Mirrors ``resolveCanonicalParentId``
        (``session-manager-core.ts:343-354``)."""
        seen: set[str] = set()
        current_id: Optional[str] = parent_id
        while current_id and current_id not in self.by_id:
            if current_id in seen:
                return None
            seen.add(current_id)
            current_id = self.opaque_parents_by_id.get(current_id)
        return current_id

    # ------------------------------------------------------------------
    # normalizeEntryParent
    # ------------------------------------------------------------------

    def normalize_entry_parent(self, entry: SessionEntry) -> SessionEntry:
        """Normalize the entry's parent id. Mirrors
        ``normalizeEntryParent``
        (``session-manager-core.ts:356-380``)."""
        if entry["id"] in self.logical_parents_by_id:
            parent_id: Optional[str] = self.logical_parents_by_id.get(entry["id"])
        else:
            parent_id = self.resolve_canonical_parent_id(entry.get("parentId"))
        normalized: SessionEntry = (
            entry if parent_id == entry.get("parentId") else {**entry, "parentId": parent_id}
        )
        if (
            normalized.get("type") == "compaction"
            and normalized.get("firstKeptEntryId") not in self.by_id
            and normalized.get("firstKeptEntryId") in self.opaque_parents_by_id
        ):
            resolved_first_kept_parent = self.resolve_canonical_parent_id(
                normalized.get("firstKeptEntryId")
            )
            first_kept_entry_id = (
                resolved_first_kept_parent
                or self._find_first_canonical_descendant_on_branch(
                    normalized["firstKeptEntryId"], normalized.get("parentId")
                )
                or self._find_first_canonical_descendant(normalized["firstKeptEntryId"])
                or parent_id
            )
            if (
                first_kept_entry_id
                and first_kept_entry_id != normalized["firstKeptEntryId"]
            ):
                normalized = {**normalized, "firstKeptEntryId": first_kept_entry_id}
        return normalized

    def _find_first_canonical_descendant_on_branch(
        self, opaque_id: str, leaf_id: Optional[str]
    ) -> Optional[str]:
        """Find the first canonical descendant on a
        branch. Mirrors
        ``findFirstCanonicalDescendantOnBranch``
        (``session-manager-core.ts:382-403``)."""
        seen: set[str] = set()
        current_id: Optional[str] = leaf_id
        first_canonical_descendant: Optional[str] = None
        while current_id and current_id not in seen:
            if current_id == opaque_id:
                return first_canonical_descendant
            seen.add(current_id)
            entry = self.by_id.get(current_id)
            if entry is not None:
                first_canonical_descendant = entry["id"]
                current_id = entry.get("parentId")
            else:
                current_id = self.opaque_parents_by_id.get(current_id)
        return None

    def _find_first_canonical_descendant(self, opaque_id: str) -> Optional[str]:
        """Find the first canonical descendant
        anywhere. Mirrors
        ``findFirstCanonicalDescendant``
        (``session-manager-core.ts:405-421``)."""
        for entry in self.file_entries:
            if not is_indexed_session_entry(entry):
                continue
            seen: set[str] = set()
            parent_id: Optional[str] = entry.get("parentId")
            while (
                parent_id
                and parent_id in self.opaque_parents_by_id
                and parent_id not in seen
            ):
                if parent_id == opaque_id:
                    return entry["id"]
                seen.add(parent_id)
                parent_id = self.opaque_parents_by_id.get(parent_id)
        return None

    # ------------------------------------------------------------------
    # resolveBranchTargetId
    # ------------------------------------------------------------------

    def resolve_branch_target_id(
        self, branch_from_id: str
    ) -> Optional[str]:
        """Resolve a branch-target id. Mirrors
        ``resolveBranchTargetId``
        (``session-manager-core.ts:423-431``)."""
        if branch_from_id in self.by_id:
            return branch_from_id
        if branch_from_id not in self.opaque_parents_by_id:
            return None
        return self.resolve_canonical_parent_id(branch_from_id)

    # ------------------------------------------------------------------
    # clampOpaqueFileEntryIndexes
    # ------------------------------------------------------------------

    def clamp_opaque_file_entry_indexes(self) -> None:
        """Clamp the opaque-entry indexes to the
        current file-entries range. Mirrors
        ``clampOpaqueFileEntryIndexes``
        (``session-manager-core.ts:433-442``)."""
        previous_opaque_index = 0
        for opaque_entry in self.opaque_file_entries:
            idx = opaque_entry.get("index", 0)
            opaque_entry["index"] = max(
                previous_opaque_index, min(idx, len(self.file_entries))
            )
            previous_opaque_index = opaque_entry["index"]

    # ------------------------------------------------------------------
    # createLeafControl / rememberLeafControl
    # ------------------------------------------------------------------

    def create_leaf_control(
        self,
        parent_id: Optional[str],
        append_parent_id: Optional[str] = None,
        append_mode: Optional[Literal["side"]] = None,
    ) -> SessionLeafControl:
        """Create a fresh leaf control. Mirrors
        ``createLeafControl``
        (``session-manager-core.ts:444-460``)."""
        if append_parent_id is None:
            append_parent_id = self.append_parent_id
        has_id = lambda id_: id_ in self.by_id or id_ in self.opaque_parents_by_id
        leaf: SessionLeafControl = {
            "type": "leaf",
            "id": generate_session_entry_id(has_id),
            "parentId": parent_id,
            "timestamp": _now_iso(),
            "targetId": self.leaf_id,
        }
        if append_parent_id != self.leaf_id:
            leaf["appendParentId"] = append_parent_id
        if append_mode:
            leaf["appendMode"] = append_mode
        return leaf

    def remember_leaf_control(self, leaf_entry: SessionLeafControl) -> None:
        """Record a leaf control in the opaque
        entries. Mirrors ``rememberLeafControl``
        (``session-manager-core.ts:462-465``)."""
        self.opaque_file_entries.append(
            {"index": len(self.file_entries), "record": leaf_entry}
        )
        self.opaque_parents_by_id[leaf_entry["id"]] = self.leaf_id

    # ------------------------------------------------------------------
    # getPersistedFileEntries
    # ------------------------------------------------------------------

    def get_persisted_file_entries(
        self,
        leaf_append_parent_id: Optional[str] = None,
        leaf_append_mode: Optional[Literal["side"]] = None,
    ) -> list[Any]:
        """Return the entries to be persisted. Mirrors
        ``getPersistedFileEntries``
        (``session-manager-core.ts:467-525``)."""
        if leaf_append_parent_id is None:
            leaf_append_parent_id = self.append_parent_id
        self.clamp_opaque_file_entry_indexes()
        entries: list[Any] = []
        opaque_index = 0
        for index in range(len(self.file_entries) + 1):
            while (
                opaque_index < len(self.opaque_file_entries)
                and self.opaque_file_entries[opaque_index].get("index") == index
            ):
                entries.append(self.opaque_file_entries[opaque_index].get("record"))
                opaque_index += 1
            entry = self.file_entries[index] if index < len(self.file_entries) else None
            if entry is not None:
                entries.append(entry)
        while opaque_index < len(self.opaque_file_entries):
            entries.append(self.opaque_file_entries[opaque_index].get("record"))
            opaque_index += 1

        persisted_leaf_id: Optional[str] = None
        persisted_append_parent_id: Optional[str] = None
        raw_tail_id: Optional[str] = None
        for entry in entries:
            leaf_entry = parse_opaque_leaf_entry(entry)
            if leaf_entry:
                raw_tail_id = leaf_entry["id"]
                if leaf_entry["id"] in self.invalid_leaf_control_ids:
                    continue
                target_id = self.resolve_opaque_leaf_target_id(leaf_entry.get("targetId"))
                persisted_leaf_id = target_id
                persisted_append_parent_id = (
                    self.resolve_opaque_append_parent_id(leaf_entry.get("appendParentId"))
                    if leaf_entry.get("appendParentId") is not None
                    else target_id
                )
                continue
            if is_indexed_session_entry(entry):
                persisted_leaf_id = entry["id"]
                persisted_append_parent_id = entry["id"]
                raw_tail_id = entry["id"]
                continue
            opaque_link = parse_parent_linked_opaque_entry(entry)
            if opaque_link is not None:
                persisted_append_parent_id = opaque_link["id"]
                raw_tail_id = opaque_link["id"]
        if (
            persisted_leaf_id != self.leaf_id
            or persisted_append_parent_id != self.append_parent_id
        ):
            leaf_entry = self.create_leaf_control(
                raw_tail_id, leaf_append_parent_id, leaf_append_mode
            )
            self.remember_leaf_control(leaf_entry)
            entries.append(leaf_entry)
        return entries

    def get_serialized_file_lines_for_rewrite(self) -> list[str]:
        """Return the JSONL lines to rewrite the
        session file. Mirrors
        ``getSerializedFileLinesForRewrite``
        (``session-manager-core.ts:527-529``)."""
        return [json.dumps(entry) for entry in self.get_persisted_file_entries()]

    def clear_preserved_opaque_file_entries(self) -> None:
        """Drop all preserved opaque entries. Mirrors
        ``clearPreservedOpaqueFileEntries``
        (``session-manager-core.ts:531-537``)."""
        self.opaque_file_entries = []
        self.opaque_parents_by_id.clear()
        self.invalid_leaf_control_ids.clear()
        self.append_parent_id = None
        self.prompt_released_side_branch_parent_id = None

    # ------------------------------------------------------------------
    # writeFullFile / replacePersistedTranscript
    # ------------------------------------------------------------------

    def write_full_file(
        self,
        leaf_append_parent_id: Optional[str] = None,
        leaf_append_mode: Optional[Literal["side"]] = None,
    ) -> str:
        """Write the full session file. Mirrors
        ``writeFullFile``
        (``session-manager-core.ts:539-549``)."""
        if not self.session_file:
            return ""
        entries = self.get_persisted_file_entries(
            leaf_append_parent_id, leaf_append_mode
        )
        content = "\n".join(json.dumps(e) for e in entries) + "\n"
        with open(self.session_file, "w", encoding="utf-8") as f:
            f.write(content)
        return content

    def replace_persisted_transcript(
        self,
        options: Optional[dict] = None,
    ) -> None:
        """Rewrite the on-disk transcript with the
        current entries. Mirrors
        ``replacePersistedTranscript``
        (``session-manager-core.ts:551-583``)."""
        options = options or {}
        leaf_append_parent_id = options.get(
            "leafAppendParentId", self.append_parent_id
        )
        leaf_append_mode = options.get("leafAppendMode")
        publish_snapshot = options.get("publishSnapshot", True)
        if not self.should_persist:
            return
        if self.sqlite_persistence:
            # Phase 6.5 wires the SQLite transcript
            # rewrite. For now the SQLite path is a
            # no-op (the file is the source of
            # truth during Phase 6.4).
            self.flushed = True
            return
        if not self.session_file:
            return
        content = self.write_full_file(leaf_append_parent_id, leaf_append_mode)
        remembered_write = remember_written_session_entries(
            self.session_file, content
        )
        self.session_file_snapshot = remembered_write["snapshot"]
        if remembered_write["verifiedWrite"] and publish_snapshot:
            publish_remembered_session_file_snapshot(
                self.session_file, remembered_write["snapshot"]
            )

    # ------------------------------------------------------------------
    # Getters
    # ------------------------------------------------------------------

    def is_persisted(self) -> bool:
        return self.should_persist

    def get_cwd(self) -> str:
        return self.cwd

    def get_session_dir(self) -> str:
        return self.session_dir

    def get_session_id(self) -> str:
        return self.session_id

    def was_recovered_from_corrupt_header(self) -> bool:
        return self.recovered_corrupt_header

    def get_session_file(self) -> Optional[str]:
        return self.session_file


# ----------------------------------------------------------------------------
# Helper: detect side-append entries.
# ----------------------------------------------------------------------------


def _is_session_transcript_side_append_entry(entry: Any) -> bool:
    """True iff ``entry`` is a transcript side-append
    entry. Mirrors
    ``isSessionTranscriptSideAppendEntry``
    (``openclaw-main/src/config/sessions/transcript-tree.ts``).

    Phase 6.4a ships a minimal port: the only
    side-append discriminator we know about
    here is the ``appendMode === "side"`` field
    on a :class:`SessionLeafControl`. The full
    transcript-side-append detection (which
    spans ``branch_summary`` + side-leaf
    composites) lands in Phase 6.5 with the
    full transcript tree port.
    """
    if not isinstance(entry, dict):
        return False
    if entry.get("appendMode") == "side":
        return True
    return False


# Add the Literal import at module scope so the
# type annotations in :meth:`create_leaf_control`
# and :meth:`get_persisted_file_entries` resolve.
from typing import Literal  # noqa: E402


__all__ = [
    "SessionManagerCore",
    "SqliteSessionManagerPersistence",
]
