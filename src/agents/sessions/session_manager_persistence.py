"""jarvis.agents.sessions.session_manager_persistence — persistence layer.

OpenClaw parity: mirrors
``openclaw-main/src/agents/sessions/session-manager-persistence.ts``.

Adds the persistence layer on top of
:class:`SessionManagerCore`. The
:class:`SessionManagerPersistence` class owns
the file-append + cache-invalidation logic,
the ``removeTrailingEntries`` rewrite path,
the ``syncSnapshotAfterHeaderRewrite``
post-rewrite sync helper, and the
``mergePromptReleasedSessionEntries`` side-
branch merge.

Phase 6.4b — session persistence.

Adaptations
-----------
- The OpenClaw source's
  ``appendTranscriptEventSync`` /
  ``appendTranscriptMessageSync`` /
  ``replaceTranscriptEventsSync`` come from
  ``config/sessions/session-accessor.ts``. The
  Python port ships the file-only path; the
  SQLite path remains a Phase-6.5 stub (the
  full transcript-DB rewrite lands with
  ``createAgentSession`` + the AgentSession
  family).
- The OpenClaw source's
  ``appendSerializedJsonlEntrySync`` /
  ``serializeJsonlEntry`` /
  ``writeJsonlEntriesSync`` come from
  ``config/sessions/transcript-jsonl.ts``. The
  Python port uses :mod:`json` directly
  (matching the file-only path).
- The OpenClaw source's
  ``isSessionTranscriptSideAppendEntry`` comes
  from ``config/sessions/transcript-tree.ts``.
  The Python port ships a minimal local
  detector that handles the
  ``appendMode === "side"`` discriminator; the
  full transcript-tree detection lands in
  Phase 6.5.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Callable, Optional

from .session_manager_core import (
    SessionManagerCore,
    _is_session_transcript_side_append_entry,
)
from .session_manager_file import (
    LoadedSessionFile,
    can_publish_owned_session_append,
    json_serialization_can_run_user_code,
    publish_remembered_session_file_snapshot,
    read_session_file_snapshot_if_exists,
    remember_appended_session_entry,
    remember_written_session_entries,
    revalidate_loaded_session_file,
    session_file_needs_append_separator,
)
from .session_manager_codec import (
    is_indexed_session_entry,
    is_json_record,
    parse_opaque_leaf_entry,
    parse_parent_linked_opaque_entry,
)
from .session_manager_types import (
    AppendPersistenceOptions,
    PromptReleasedSessionEntry,
    PromptReleasedSessionMergeResult,
    SessionEntry,
)


_LOG = logging.getLogger("jarvis.agents.sessions.session_manager_persistence")


def _serialize_jsonl_entry(entry: Any) -> str:
    """Serialize a single entry to a JSONL line.
    Mirrors ``serializeJsonlEntry``
    (``config/sessions/transcript-jsonl.ts``).

    Phase 6.4b ships the file-only path; the
    full transcript-DB serialize lives in
    Phase 6.5.
    """
    return json.dumps(entry, ensure_ascii=False)


def _append_serialized_jsonl_entry_sync(
    file_path: str, serialized_entry: str, options: Optional[dict] = None
) -> str:
    """Append a serialized entry to a session
    file. Mirrors
    ``appendSerializedJsonlEntrySync``
    (``config/sessions/transcript-jsonl.ts``).

    Returns the full ``serializedAppend`` that
    was written (``\\n + serialized_entry`` if
    a prefix newline was needed, else
    ``serialized_entry`` alone).
    """
    options = options or {}
    prefix_newline = options.get("prefixNewline", True)
    content: str
    if prefix_newline and not serialized_entry.startswith("\n"):
        content = "\n" + serialized_entry
    else:
        content = serialized_entry
    with open(file_path, "ab") as f:
        f.write(content.encode("utf-8"))
    return content


class SessionManagerPersistence(SessionManagerCore):
    """Persistence layer on top of
    :class:`SessionManagerCore`. Mirrors
    ``SessionManagerPersistence``
    (``session-manager-persistence.ts:34-431``).

    Adds:
    - ``remove_trailing_entries`` — drop the
      tail of the file-entries that match a
      predicate (preserving optional
      ``preserveTrailing`` matches).
    - ``persist_record`` — write a single
      record to disk (the first-ever persist
      writes the full file; subsequent persists
      append + update the cache).
    - ``persist`` — public entry point for
      :meth:`SessionManagerCore` callers.
    - ``sync_snapshot_after_header_rewrite``
      — post-rewrite cache sync.
    - ``merge_prompt_released_session_entries``
      — merge a batch of side-branch entries
      that came back from a prompt-released
      agent.
    """

    # ------------------------------------------------------------------
    # removeTrailingEntries
    # ------------------------------------------------------------------

    def remove_trailing_entries(
        self,
        predicate: Callable[[SessionEntry], bool],
        options: Optional[dict] = None,
    ) -> int:
        """Remove trailing file-entries that match
        ``predicate``. Mirrors
        ``removeTrailingEntries``
        (``session-manager-persistence.ts:35-143``)."""
        options = options or {}
        preserve_trailing = options.get("preserveTrailing")
        preserved_start = len(self.file_entries)
        while preserved_start > 1:
            entry = self.file_entries[preserved_start - 1]
            if (
                not is_indexed_session_entry(entry)
                or not (preserve_trailing and preserve_trailing(entry))
            ):
                break
            preserved_start -= 1

        remove_start = preserved_start
        while remove_start > 1:
            entry = self.file_entries[remove_start - 1]
            if (
                not is_indexed_session_entry(entry)
                or not predicate(entry)
            ):
                break
            remove_start -= 1
        if remove_start == preserved_start:
            return 0

        def shift_opaque_indexes_after_removal(start: int, count: int) -> None:
            for opaque_entry in self.opaque_file_entries:
                removed_before_opaque = max(
                    0, min(count, opaque_entry.get("index", 0) - start)
                )
                opaque_entry["index"] = (
                    opaque_entry.get("index", 0) - removed_before_opaque
                )

        removed_count = preserved_start - remove_start
        shift_opaque_indexes_after_removal(remove_start, removed_count)
        removed_entries = self.file_entries[remove_start : remove_start + removed_count]
        del self.file_entries[remove_start : remove_start + removed_count]
        removed_parent_by_id: dict[str, Optional[str]] = {
            e["id"]: e.get("parentId") for e in removed_entries
        }
        index = remove_start
        while index < len(self.file_entries):
            entry = self.file_entries[index]
            if (
                is_indexed_session_entry(entry)
                and entry.get("type") == "label"
                and entry.get("targetId") in removed_parent_by_id
            ):
                removed_parent_by_id[entry["id"]] = entry.get("parentId")
                shift_opaque_indexes_after_removal(index, 1)
                del self.file_entries[index]
                continue
            index += 1

        def resolve_retained_parent_id(parent_id: Optional[str]) -> Optional[str]:
            seen: set[str] = set()
            current_id: Optional[str] = parent_id
            while current_id and current_id in removed_parent_by_id and current_id not in seen:
                seen.add(current_id)
                current_id = removed_parent_by_id.get(current_id)
            return current_id

        replacement_parent_id = resolve_retained_parent_id(
            removed_entries[0].get("parentId") if removed_entries else None
        )
        new_file_entries: list[Any] = []
        for entry in self.file_entries:
            if not is_indexed_session_entry(entry):
                new_file_entries.append(entry)
                continue
            parent_id = resolve_retained_parent_id(entry.get("parentId"))
            if parent_id == entry.get("parentId"):
                new_file_entries.append(entry)
            else:
                new_file_entries.append({**entry, "parentId": parent_id})
        self.file_entries = new_file_entries

        new_opaque_entries: list[dict] = []
        for opaque_entry in self.opaque_file_entries:
            record = opaque_entry.get("record")
            if not is_json_record(record):
                new_opaque_entries.append(opaque_entry)
                continue
            raw_parent_id = record.get("parentId")
            new_parent_id: Optional[str] = None
            if raw_parent_id is None:
                new_parent_id = None
            elif isinstance(raw_parent_id, str):
                new_parent_id = resolve_retained_parent_id(raw_parent_id)
            # When raw_parent_id is neither None
            # nor a string, the OpenClaw source
            # leaves the entry's parentId alone.
            leaf_entry = parse_opaque_leaf_entry(record)
            target_id: Optional[str] = None
            append_parent_id: Optional[str] = None
            if leaf_entry is not None:
                target_id = resolve_retained_parent_id(leaf_entry.get("targetId"))
                if leaf_entry.get("appendParentId") is not None:
                    append_parent_id = resolve_retained_parent_id(
                        leaf_entry.get("appendParentId")
                    )
            parent_changed = (
                new_parent_id is not None and new_parent_id != raw_parent_id
            ) or (
                raw_parent_id is None
                and new_parent_id is None
                and False
            )
            target_changed = (
                target_id is not None
                and target_id != (leaf_entry.get("targetId") if leaf_entry else None)
            )
            append_changed = (
                append_parent_id is not None
                and append_parent_id
                != (leaf_entry.get("appendParentId") if leaf_entry else None)
            )
            if not parent_changed and not target_changed and not append_changed:
                new_opaque_entries.append(opaque_entry)
                continue
            new_record: dict = {**record}
            if parent_changed and new_parent_id is not None:
                new_record["parentId"] = new_parent_id
            if target_changed and target_id is not None:
                new_record["targetId"] = target_id
            if append_changed and append_parent_id is not None:
                new_record["appendParentId"] = append_parent_id
            new_opaque_entries.append({**opaque_entry, "record": new_record})
        self.opaque_file_entries = new_opaque_entries

        self.clamp_opaque_file_entry_indexes()
        self.build_index()
        self.leaf_id = self.resolve_canonical_parent_id(replacement_parent_id)
        self.append_parent_id = replacement_parent_id
        self.replace_persisted_transcript()
        return len(removed_entries)

    # ------------------------------------------------------------------
    # persistRecord / persist
    # ------------------------------------------------------------------

    def persist_record(
        self,
        entry: Any,
        options: Optional[AppendPersistenceOptions] = None,
        publish_snapshot: bool = True,
    ) -> None:
        """Persist a single record. Mirrors
        ``persistRecord``
        (``session-manager-persistence.ts:145-210``)."""
        if self.sqlite_persistence:
            self._persist_sqlite_record(entry, options)
            return
        if not self.should_persist or not self.session_file:
            return

        # The OpenClaw source's
        # ``hasAssistant`` short-circuit: the
        # file is not flushed until the first
        # assistant message has been appended.
        has_assistant = any(
            is_indexed_session_entry(file_entry)
            and file_entry.get("type") == "message"
            and isinstance(file_entry.get("message"), dict)
            and file_entry["message"].get("role") == "assistant"
            for file_entry in self.file_entries
        )
        if not has_assistant:
            self.flushed = False
            return

        if not self.flushed:
            content = self.write_full_file()
            self.flushed = True
            remembered_write = remember_written_session_entries(
                self.session_file, content
            )
            self.session_file_snapshot = remembered_write["snapshot"]
            if remembered_write["verifiedWrite"] and publish_snapshot:
                publish_remembered_session_file_snapshot(
                    self.session_file, remembered_write["snapshot"]
                )
            return

        serialization_can_run_user_code = json_serialization_can_run_user_code(entry)
        serialized_entry = _serialize_jsonl_entry(entry)
        before_append_snapshot = read_session_file_snapshot_if_exists(
            self.session_file
        )
        invalidate_serialized_prefix_cache = (
            (options.invalidate_serialized_prefix_cache
             if options is not None else False)
            or serialization_can_run_user_code
        )
        can_publish_owned_append = (
            not serialization_can_run_user_code
            and can_publish_owned_session_append(
                self.session_file, before_append_snapshot
            )
        )
        cache_owned_append = (
            can_publish_owned_append and not invalidate_serialized_prefix_cache
        )
        serialized_append = _append_serialized_jsonl_entry_sync(
            self.session_file,
            serialized_entry,
            {
                "prefixNewline": session_file_needs_append_separator(
                    self.session_file, before_append_snapshot
                ),
            },
        )
        remembered_append = remember_appended_session_entry(
            {
                "file_path": self.session_file,
                "previousSnapshot": self.session_file_snapshot,
                "beforeAppendSnapshot": before_append_snapshot,
                "serializedAppend": serialized_append,
                "cacheOwnedAppend": cache_owned_append,
                "publishOwnedAppend": can_publish_owned_append,
                "invalidateSerializedPrefixCache": invalidate_serialized_prefix_cache,
            }
        )
        self.session_file_snapshot = remembered_append["snapshot"]
        if remembered_append["ownedAppendVerified"] and publish_snapshot:
            publish_remembered_session_file_snapshot(
                self.session_file, remembered_append["snapshot"]
            )
        elif cache_owned_append:
            self.set_loaded_session_file(
                self.session_file,
                revalidate_loaded_session_file(
                    self.session_file,
                    LoadedSessionFile(
                        entries=self.file_entries,
                        snapshot=before_append_snapshot,
                    ),
                ),
            )

    def persist(
        self,
        entry: SessionEntry,
        options: Optional[AppendPersistenceOptions] = None,
    ) -> None:
        """Public entry point for :meth:`persist_record`. Mirrors
        ``persist``
        (``session-manager-persistence.ts:212-214``)."""
        self.persist_record(entry, options)

    def _persist_sqlite_record(
        self,
        entry: Any,
        options: Optional[AppendPersistenceOptions] = None,
    ) -> None:
        """Append one session entry to the per-agent SQLite database."""
        from jarvis_state_core import append_agent_session_entry, open_agent_database

        if not isinstance(entry, dict):
            raise TypeError("SQLite session entries must be dictionaries")
        handle = open_agent_database(
            {
                "agent_id": str(self.sqlite_persistence.get("agent_id", "")),
                "path": str(self.sqlite_persistence.get("store_path", "")),
            }
        )
        session_id = str(self.sqlite_persistence.get("session_id") or self.session_id)
        timestamp = str(entry.get("timestamp") or "")
        if entry.get("type") == "session":
            from jarvis_state_core import ensure_agent_session

            ensure_agent_session(handle, session_id, self.cwd, timestamp)
            return
        append_agent_session_entry(handle, session_id, entry, timestamp)

    # ------------------------------------------------------------------
    # syncSnapshotAfterHeaderRewrite
    # ------------------------------------------------------------------

    def sync_snapshot_after_header_rewrite(
        self, expected_content: Optional[str] = None
    ) -> None:
        """Sync the snapshot cache after a
        full-file rewrite. Mirrors
        ``syncSnapshotAfterHeaderRewrite``
        (``session-manager-persistence.ts:247-256``)."""
        if not self.session_file:
            return
        remembered_write = remember_written_session_entries(
            self.session_file, expected_content
        )
        self.session_file_snapshot = remembered_write["snapshot"]
        if remembered_write["verifiedWrite"]:
            publish_remembered_session_file_snapshot(
                self.session_file, remembered_write["snapshot"]
            )

    # ------------------------------------------------------------------
    # mergePromptReleasedSessionEntries
    # ------------------------------------------------------------------

    def merge_prompt_released_session_entries(
        self,
        entries: list[PromptReleasedSessionEntry],
        options: Optional[dict] = None,
    ) -> Optional[PromptReleasedSessionMergeResult]:
        """Merge a batch of side-branch entries
        that came back from a prompt-released
        agent. Mirrors
        ``mergePromptReleasedSessionEntries``
        (``session-manager-persistence.ts:258-397``)."""
        options = options or {}
        self._assert_prompt_released_entries_preserve_active_leaf(entries)
        side_branch_parent_id: Optional[str] = (
            self.prompt_released_side_branch_parent_id
            if self.prompt_released_side_branch_parent_id is not None
            else self.leaf_id
        )
        persisted_leaf_id: Optional[str] = self.leaf_id
        persisted_append_parent_id: Optional[str] = self.append_parent_id
        persisted_append_mode: str = (
            "side" if self.prompt_released_side_branch_parent_id is not None else "active"
        )
        saw_persisted_state_update = False
        raw_tail_id: Optional[str] = None

        for source_entry in entries:
            if source_entry.get("type") == "prompt_released_opaque":
                self.opaque_file_entries.append(
                    {
                        "index": len(self.file_entries),
                        "record": source_entry["record"],
                    }
                )
                leaf_entry = parse_opaque_leaf_entry(source_entry["record"])
                if leaf_entry is not None:
                    raw_tail_id = leaf_entry["id"]
                    leaf_state = self.resolve_opaque_leaf_control(leaf_entry)
                    if not leaf_state:
                        self.invalid_leaf_control_ids.add(leaf_entry["id"])
                        self.opaque_parents_by_id[leaf_entry["id"]] = (
                            self.resolve_opaque_append_parent_id(
                                leaf_entry.get("parentId")
                            )
                        )
                        continue
                    self.opaque_parents_by_id[leaf_entry["id"]] = leaf_state["leafId"]
                    side_branch_parent_id = leaf_state["appendParentId"]
                    persisted_leaf_id = leaf_state["leafId"]
                    persisted_append_parent_id = leaf_state["appendParentId"]
                    persisted_append_mode = (
                        "side" if leaf_state.get("appendMode") == "side" else "active"
                    )
                    saw_persisted_state_update = True
                    continue
                link = parse_parent_linked_opaque_entry(source_entry["record"])
                if link is not None:
                    self.opaque_parents_by_id[link["id"]] = link["parentId"]
                    side_branch_parent_id = link["id"]
                    persisted_append_parent_id = link["id"]
                    saw_persisted_state_update = True
                    raw_tail_id = link["id"]
                continue

            if source_entry["id"] in self.by_id:
                raise RuntimeError(f"Entry {source_entry['id']} already exists")
            if (
                source_entry.get("type") == "label"
                and source_entry.get("targetId") not in self.by_id
            ):
                raise RuntimeError(
                    f"Entry {source_entry.get('targetId')} not found"
                )
            entry_dict: dict = {**source_entry, "parentId": side_branch_parent_id}
            self.file_entries.append(entry_dict)
            self.by_id[entry_dict["id"]] = entry_dict
            side_branch_parent_id = entry_dict["id"]
            persisted_append_parent_id = entry_dict["id"]
            if _is_session_transcript_side_append_entry(entry_dict):
                persisted_append_mode = "side"
            else:
                persisted_leaf_id = entry_dict["id"]
                persisted_append_mode = "active"
            saw_persisted_state_update = True
            raw_tail_id = entry_dict["id"]
            if entry_dict.get("type") == "label":
                target_id = entry_dict.get("targetId")
                if entry_dict.get("label"):
                    if isinstance(target_id, str):
                        self.labels_by_id[target_id] = entry_dict["label"]
                        self.label_timestamps_by_id[target_id] = entry_dict.get(
                            "timestamp", ""
                        )
                else:
                    if isinstance(target_id, str):
                        self.labels_by_id.pop(target_id, None)
                        self.label_timestamps_by_id.pop(target_id, None)

        self.prompt_released_side_branch_parent_id = side_branch_parent_id
        if self.session_file:
            self.session_file_snapshot = read_session_file_snapshot_if_exists(
                self.session_file
            )
        if (
            options.get("persistLeaf") is not True
            or not self.should_persist
            or not self.session_file
            or not saw_persisted_state_update
            or (
                persisted_leaf_id == self.leaf_id
                and persisted_append_parent_id == side_branch_parent_id
                and persisted_append_mode == "side"
            )
        ):
            return None

        has_assistant = any(
            is_indexed_session_entry(entry)
            and entry.get("type") == "message"
            and isinstance(entry.get("message"), dict)
            and entry["message"].get("role") == "assistant"
            for entry in self.file_entries
        )
        if self.sqlite_persistence:
            # Phase 6.5 wires the SQLite
            # transcript append. For now this is
            # a no-op (the file is the source of
            # truth during Phase 6.4).
            self.flushed = True
            return {"publishedEntries": [{"kind": "id", "id": "stub"}]}
        if not self.flushed or not has_assistant:
            self.replace_persisted_transcript(
                {
                    "publishSnapshot": False,
                    "leafAppendParentId": side_branch_parent_id,
                    "leafAppendMode": "side",
                }
            )
            self.flushed = True
            if not self.session_file_snapshot:
                raise RuntimeError(
                    f"Unable to snapshot restored session file: {self.session_file}"
                )
            return {
                "sessionFileSnapshot": self.session_file_snapshot,
                "requiresReload": True,
            }

        leaf_entry_obj = self.create_leaf_control(
            raw_tail_id, side_branch_parent_id, "side"
        )
        self.persist_record(leaf_entry_obj, None, False)
        self.remember_leaf_control(leaf_entry_obj)
        if not self.session_file_snapshot:
            raise RuntimeError(
                f"Unable to snapshot restored session file: {self.session_file}"
            )
        return {
            "sessionFileSnapshot": self.session_file_snapshot,
            "publishedEntries": [{"kind": "id", "id": leaf_entry_obj["id"]}],
        }

    def _assert_prompt_released_entries_preserve_active_leaf(
        self, entries: list[PromptReleasedSessionEntry]
    ) -> None:
        """Validate that the prompt-released
        entries do not change the active branch.
        Mirrors
        ``assertPromptReleasedEntriesPreserveActiveLeaf``
        (``session-manager-persistence.ts:399-430``)."""
        side_branch_parent_id: Optional[str] = (
            self.prompt_released_side_branch_parent_id
            if self.prompt_released_side_branch_parent_id is not None
            else self.leaf_id
        )
        for entry in entries:
            if entry.get("type") != "prompt_released_opaque":
                side_branch_parent_id = entry["id"]
                continue
            leaf = parse_opaque_leaf_entry(entry["record"])
            if leaf and entry.get("preserveActiveLeaf"):
                append_parent_id = (
                    leaf.get("appendParentId")
                    if leaf.get("appendParentId") is not None
                    else leaf.get("targetId")
                )
                if (
                    leaf.get("appendMode") != "side"
                    or leaf.get("targetId") != self.leaf_id
                    or leaf.get("parentId") != side_branch_parent_id
                    or append_parent_id != side_branch_parent_id
                ):
                    raise RuntimeError(
                        "prompt-released side leaf changed the active branch"
                    )
                continue
            link = parse_parent_linked_opaque_entry(entry["record"])
            if link is not None:
                side_branch_parent_id = link["id"]


__all__ = [
    "SessionManagerPersistence",
]
