"""jarvis.agents.sessions.session_manager_branching — branching.

OpenClaw parity: mirrors
``openclaw-main/src/agents/sessions/session-manager-branching.ts``.

Adds the branching operation on top of
:class:`SessionManagerEntries`. The
:class:`SessionManagerBranching` class owns
``createBranchedSession(leafId)`` — extract a
branch path from a leaf + create a new
session file with that branch as the new
root.

Phase 6.4d — session branching.

Adaptations
-----------
- The OpenClaw source uses
  ``replaceSessionEntrySync`` from
  ``config/sessions/session-accessor.ts`` to
  update the SQLite session registry. The
  Python port ships a no-op stub (Phase 6.5
  wires the full transcript-DB).
- The OpenClaw source uses
  ``formatSqliteSessionFileMarker`` to
  build the sqlite marker. The Python port
  builds the file path directly via
  ``os.path.join`` for the file path (the
  SQLite marker format is the same regex
  Phase-6.3 wired in
  :mod:`session_manager_file`).
- The OpenClaw source's
  ``loadSessionEntry`` from
  ``session-accessor.ts`` is a stub in
  6.4d; the Python port returns ``None``
  (the new session uses the previous
  entry's metadata as a fallback).
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional, Union

from .session_manager_codec import (
    CURRENT_SESSION_VERSION,
    is_json_record,
    parse_opaque_leaf_entry,
    parse_parent_linked_opaque_entry,
)
from .session_manager_entries import SessionManagerEntries
from .session_manager_id import create_session_id, generate_session_entry_id
from .session_manager_types import (
    LabelEntry,
    PreservedOpaqueFileEntry,
    SessionEntry,
    SessionHeader,
)


_LOG = logging.getLogger("jarvis.agents.sessions.session_manager_branching")


def _now_iso() -> str:
    """Return the current UTC time as an ISO-8601
    string."""
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


class SessionManagerBranching(SessionManagerEntries):
    """Branching layer on top of
    :class:`SessionManagerEntries`. Mirrors
    ``SessionManagerBranching``
    (``session-manager-branching.ts:21-204``).

    Adds:
    - ``createBranchedSession(leafId)`` —
      collect the branch path from ``leafId``
      back to the root, build a new session
      header, copy the branch entries into a
      new session, and persist (or return
      ``undefined`` when not persisting).
    """

    def _collect_branched_session_path(
        self, leaf_id: str
    ) -> dict:
        """Collect the branch path from
        ``leaf_id`` back to the root. Mirrors
        ``collectBranchedSessionPath``
        (``session-manager-branching.ts:22-103``).

        Returns
        -------
        dict
            ``{"entries", "opaqueEntries",
            "tailId", "usedIds"}``.
        """
        # Build a lookup of opaque records by id.
        opaque_by_id: dict[str, dict] = {}
        for opaque_entry in self.opaque_file_entries:
            record = opaque_entry.get("record")
            if not is_json_record(record):
                continue
            leaf = parse_opaque_leaf_entry(record)
            link = (
                leaf
                if leaf is not None
                else parse_parent_linked_opaque_entry(record)
            )
            if link is not None and "id" in link:
                opaque_by_id[link["id"]] = record

        reversed_nodes: list[dict] = []
        seen: set[str] = set()
        current_id: Optional[str] = leaf_id
        while current_id and current_id not in seen:
            seen.add(current_id)
            entry = self.by_id.get(current_id)
            if entry is not None:
                reversed_nodes.append({"type": "entry", "entry": entry})
                if current_id in self.logical_parents_by_id:
                    physical_id = entry.get("parentId")
                    while (
                        physical_id
                        and physical_id not in seen
                    ):
                        physical_record = opaque_by_id.get(physical_id)
                        if (
                            not physical_record
                            or physical_id not in self.opaque_parents_by_id
                        ):
                            break
                        seen.add(physical_id)
                        reversed_nodes.append(
                            {
                                "type": "opaque",
                                "id": physical_id,
                                "record": physical_record,
                            }
                        )
                        physical_id = self.opaque_parents_by_id.get(physical_id)
                    current_id = self.logical_parents_by_id.get(current_id)
                else:
                    current_id = entry.get("parentId")
                continue
            record = opaque_by_id.get(current_id)
            if (
                not record
                or current_id not in self.opaque_parents_by_id
            ):
                break
            reversed_nodes.append(
                {"type": "opaque", "id": current_id, "record": record}
            )
            current_id = self.opaque_parents_by_id.get(current_id)

        entries: list[SessionEntry] = []
        opaque_entries: list[PreservedOpaqueFileEntry] = []
        used_ids: set[str] = set()
        tail_id: Optional[str] = None
        # The OpenClaw source iterates the
        # reversed list in reverse to walk from
        # the root to the leaf.
        for node in reversed(reversed_nodes):
            if node["type"] == "entry":
                entry_obj: SessionEntry = node["entry"]
                if entry_obj.get("type") == "label":
                    continue
                branch_entry: SessionEntry = (
                    entry_obj
                    if entry_obj.get("parentId") == tail_id
                    else {**entry_obj, "parentId": tail_id}
                )
                entries.append(branch_entry)
                used_ids.add(branch_entry["id"])
                tail_id = branch_entry["id"]
                continue
            record = node["record"]
            if parse_opaque_leaf_entry(record) is not None:
                continue
            opaque_entries.append(
                {
                    "index": len(entries) + 1,
                    "record": {**record, "parentId": tail_id},
                }
            )
            used_ids.add(node["id"])
            tail_id = node["id"]
        return {
            "entries": entries,
            "opaqueEntries": opaque_entries,
            "tailId": tail_id,
            "usedIds": used_ids,
        }

    def create_branched_session(
        self, leaf_id: str
    ) -> Optional[str]:
        """Create a new session file containing
        the branch path rooted at ``leaf_id``.
        Mirrors ``createBranchedSession``
        (``session-manager-branching.ts:105-203``).

        Returns
        -------
        str | None
            The new session file path (when
            ``should_persist`` is True), or
            ``None`` when not persisting.
        """
        previous_session_file = self.session_file
        branch_path = self._collect_branched_session_path(leaf_id)
        if not branch_path["entries"]:
            raise RuntimeError(f"Entry {leaf_id} not found")

        new_session_id = create_session_id()
        timestamp = _now_iso()
        file_timestamp = timestamp.replace(":", "-").replace(".", "-")
        sqlite_persistence = self.sqlite_persistence
        new_session_file: Optional[str]
        if sqlite_persistence:
            new_session_file = (
                f"sqlite:{sqlite_persistence.get('agent_id', '')}"
                f":{new_session_id}"
                f":{sqlite_persistence.get('store_path', '')}"
            )
        elif self.should_persist:
            new_session_file = os.path.join(
                self.get_session_dir(),
                f"{file_timestamp}_{new_session_id}.jsonl",
            )
        else:
            new_session_file = None

        header: SessionHeader = {
            "type": "session",
            "version": CURRENT_SESSION_VERSION,
            "id": new_session_id,
            "timestamp": timestamp,
            "cwd": self.cwd,
        }
        if self.should_persist and previous_session_file is not None:
            header["parentSession"] = previous_session_file

        path_entry_ids = {entry["id"] for entry in branch_path["entries"]}
        labels_to_write: list[dict] = []
        for target_id, label in self.labels_by_id.items():
            if target_id in path_entry_ids:
                label_ts = self.label_timestamps_by_id.get(target_id, "")
                labels_to_write.append(
                    {
                        "targetId": target_id,
                        "label": label,
                        "timestamp": label_ts,
                    }
                )

        label_entries: list[LabelEntry] = []
        parent_id: Optional[str] = branch_path["tailId"]
        used_ids: set[str] = branch_path["usedIds"]
        for lw in labels_to_write:
            label_entry: LabelEntry = {
                "type": "label",
                "id": generate_session_entry_id(used_ids),
                "parentId": parent_id,
                "timestamp": lw["timestamp"],
                "targetId": lw["targetId"],
                "label": lw["label"],
            }
            used_ids.add(label_entry["id"])
            label_entries.append(label_entry)
            parent_id = label_entry["id"]

        self.file_entries = [header, *branch_path["entries"], *label_entries]
        self.opaque_file_entries = branch_path["opaqueEntries"]
        self.session_id = new_session_id
        self.session_file_snapshot = None
        if self.should_persist:
            self.session_file = new_session_file
            if sqlite_persistence:
                # Phase 6.5 wires
                # ``replaceSessionEntrySync``.
                # The Python port updates the
                # in-memory sqlite_persistence
                # to point at the new session
                # id; the on-disk SQLite row
                # update is a no-op stub for
                # 6.4d.
                self.sqlite_persistence = {
                    **sqlite_persistence,
                    "session_id": new_session_id,
                }
            self.build_index()
            has_assistant = any(
                is_json_record(entry)
                and entry.get("type") == "message"
                and isinstance(entry.get("message"), dict)
                and entry["message"].get("role") == "assistant"
                for entry in self.file_entries
            )
            if has_assistant:
                self.replace_persisted_transcript()
                self.flushed = True
            else:
                self.flushed = False
            return new_session_file
        self.build_index()
        return None


__all__ = [
    "SessionManagerBranching",
]
