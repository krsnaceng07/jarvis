"""jarvis.agents.sessions.session_manager_entries — entry operations.

OpenClaw parity: mirrors
``openclaw-main/src/agents/sessions/session-manager-entries.ts``.

Adds the entry-level operations on top of
:class:`SessionManagerPersistence`. The
:class:`SessionManagerEntries` class owns the
typed ``appendXxx`` methods
(``appendMessage``, ``appendThinkingLevelChange``,
``appendModelChange``, ``appendCompaction``,
``appendCustomEntry``, ``appendSessionInfo``,
``appendCustomMessageEntry``, ``appendLabelChange``),
the getters
(``getLeafId``, ``getLeafEntry``, ``getEntry``,
``getChildren``, ``getLabel``, ``getBranch``,
``getHeader``, ``getEntries``, ``getTree``,
``getSessionName``),
the tree / context builders
(``buildSessionContext``, ``getTree``),
and the branch mutators
(``branch``, ``branchWithSummary``,
``resetLeaf``).

Phase 6.4c — session entry operations.

Adaptations
-----------
- The OpenClaw source's ``buildCoreSessionContext``
  from ``../runtime/index.js`` is a TS type
  conversion + tree walk over
  :class:`SessionTreeEntry`. The Python port
  uses the dict-based projection from
  Phase 6.2's
  :func:`jarvis.agents.sessions.session_manager_codec.build_session_context`
  which walks the parent chain via the
  in-memory index.
- The OpenClaw source's
  ``Message | CustomMessage | BashExecutionMessage``
  is the typed LLM message shape. The Python
  port uses dict-based message entries (the
  conversion happens at the LLM-client
  boundary in 6.12+).
- The OpenClaw source's
  ``TextContent | ImageContent`` from
  ``llm/types.ts`` is a typed content-block
  union. The Python port uses
  ``str | list[dict]`` (a string for plain
  text, a list of dicts for structured
  content).
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Optional, Union

from .session_manager_codec import (
    build_session_context,
    is_indexed_session_entry,
)
from .session_manager_core import (
    _is_session_transcript_side_append_entry,
)
from .session_manager_file import message_serializes_owned_values
from .session_manager_id import generate_session_entry_id
from .session_manager_persistence import SessionManagerPersistence
from .session_manager_types import (
    BranchSummaryEntry,
    CompactionEntry,
    CustomEntry,
    CustomMessageEntry,
    LabelEntry,
    ModelChangeEntry,
    SessionContext,
    SessionEntry,
    SessionHeader,
    SessionInfoEntry,
    SessionMessageEntry,
    SessionTreeNode,
    ThinkingLevelChangeEntry,
)


_LOG = logging.getLogger("jarvis.agents.sessions.session_manager_entries")


def _now_iso() -> str:
    """Return the current UTC time as an ISO-8601
    string. Mirrors the OpenClaw source's
    ``new Date().toISOString()``."""
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


class SessionManagerEntries(SessionManagerPersistence):
    """Entry operations on top of
    :class:`SessionManagerPersistence`. Mirrors
    ``SessionManagerEntries``
    (``session-manager-entries.ts:28-330``).

    Adds:
    - ``append_entry(entry, options?)`` —
      shared append path used by every typed
      ``appendXxx`` helper.
    - ``appendMessage(message, options?)`` /
      ``appendThinkingLevelChange(level)`` /
      ``appendModelChange(provider, modelId)`` /
      ``appendCompaction(summary, firstKeptEntryId, tokensBefore, details?, fromHook?)`` /
      ``appendCustomEntry(customType, data?)`` /
      ``appendSessionInfo(name)`` /
      ``appendCustomMessageEntry(customType, content, display, details?)`` /
      ``appendLabelChange(targetId, label)``.
    - ``getLeafId()`` /
      ``getLeafEntry()`` /
      ``getEntry(id)`` /
      ``getChildren(parentId)`` /
      ``getLabel(id)`` /
      ``getBranch(fromId?)`` /
      ``getHeader()`` /
      ``getEntries()`` /
      ``getTree()`` /
      ``getSessionName()`` /
      ``buildSessionContext()``.
    - ``branch(branchFromId)`` /
      ``branchWithSummary(branchFromId, summary, details?, fromHook?)`` /
      ``resetLeaf()``.
    """

    # ------------------------------------------------------------------
    # appendEntry
    # ------------------------------------------------------------------

    def append_entry(
        self,
        entry: SessionEntry,
        options: Optional[Any] = None,
    ) -> None:
        """Append a single entry to the in-memory
        state + persist it. Mirrors
        ``appendEntry``
        (``session-manager-entries.ts:29-43``)."""
        if (
            not _is_session_transcript_side_append_entry(entry)
            and entry.get("parentId") == self.append_parent_id
            and self.leaf_id != self.append_parent_id
        ):
            self.logical_parents_by_id[entry["id"]] = self.leaf_id
        self.file_entries.append(entry)
        self.by_id[entry["id"]] = entry
        self.leaf_id = entry["id"]
        self.append_parent_id = entry["id"]
        self.prompt_released_side_branch_parent_id = None
        self.persist(entry, options)

    # ------------------------------------------------------------------
    # Typed append helpers
    # ------------------------------------------------------------------

    def append_message(
        self,
        message: dict,
        options: Optional[Any] = None,
    ) -> str:
        """Append a message entry. Mirrors
        ``appendMessage``
        (``session-manager-entries.ts:45-60``)."""
        invalidate_serialized_prefix_cache = False
        if options is not None and getattr(options, "invalidate_serialized_prefix_cache", None):
            invalidate_serialized_prefix_cache = True
        if message_serializes_owned_values(message):
            invalidate_serialized_prefix_cache = True
        entry: SessionMessageEntry = {
            "type": "message",
            "id": generate_session_entry_id(self.by_id),
            "parentId": self.append_parent_id,
            "timestamp": _now_iso(),
            "message": message,
        }
        opts: Any = options
        if invalidate_serialized_prefix_cache and opts is not None:
            try:
                opts = type(opts)(
                    **{**opts.__dict__, "invalidate_serialized_prefix_cache": True}
                )
            except Exception:
                opts = None
        elif invalidate_serialized_prefix_cache:
            opts = type("AppendOpts", (), {
                "invalidate_serialized_prefix_cache": True,
            })()
        self.append_entry(entry, opts)
        return entry["id"]

    def append_thinking_level_change(self, thinking_level: str) -> str:
        """Append a thinking-level change entry. Mirrors
        ``appendThinkingLevelChange``
        (``session-manager-entries.ts:62-72``)."""
        entry: ThinkingLevelChangeEntry = {
            "type": "thinking_level_change",
            "id": generate_session_entry_id(self.by_id),
            "parentId": self.append_parent_id,
            "timestamp": _now_iso(),
            "thinkingLevel": thinking_level,
        }
        self.append_entry(entry)
        return entry["id"]

    def append_model_change(self, provider: str, model_id: str) -> str:
        """Append a model change entry. Mirrors
        ``appendModelChange``
        (``session-manager-entries.ts:74-85``)."""
        entry: ModelChangeEntry = {
            "type": "model_change",
            "id": generate_session_entry_id(self.by_id),
            "parentId": self.append_parent_id,
            "timestamp": _now_iso(),
            "provider": provider,
            "modelId": model_id,
        }
        self.append_entry(entry)
        return entry["id"]

    def append_compaction(
        self,
        summary: str,
        first_kept_entry_id: str,
        tokens_before: int,
        details: Optional[Any] = None,
        from_hook: Optional[bool] = None,
    ) -> str:
        """Append a compaction entry. Mirrors
        ``appendCompaction``
        (``session-manager-entries.ts:87-109``)."""
        entry: CompactionEntry = {
            "type": "compaction",
            "id": generate_session_entry_id(self.by_id),
            "parentId": self.append_parent_id,
            "timestamp": _now_iso(),
            "summary": summary,
            "firstKeptEntryId": first_kept_entry_id,
            "tokensBefore": tokens_before,
        }
        if details is not None:
            entry["details"] = details
        if from_hook is not None:
            entry["fromHook"] = from_hook
        invalidate_cache = (from_hook is True) or (details is not None)
        opts: Any = None
        if invalidate_cache:
            opts = type("AppendOpts", (), {
                "invalidate_serialized_prefix_cache": True,
            })()
        self.append_entry(entry, opts)
        return entry["id"]

    def append_custom_entry(
        self, custom_type: str, data: Optional[Any] = None
    ) -> str:
        """Append a custom entry. Mirrors
        ``appendCustomEntry``
        (``session-manager-entries.ts:111-122``)."""
        entry: CustomEntry = {
            "type": "custom",
            "customType": custom_type,
            "data": data,
            "id": generate_session_entry_id(self.by_id),
            "parentId": self.append_parent_id,
            "timestamp": _now_iso(),
        }
        opts = type("AppendOpts", (), {
            "invalidate_serialized_prefix_cache": True,
        })()
        self.append_entry(entry, opts)
        return entry["id"]

    def append_session_info(self, name: str) -> str:
        """Append a session-info entry. Mirrors
        ``appendSessionInfo``
        (``session-manager-entries.ts:124-134``)."""
        # The OpenClaw source strips CR/LF and
        # trims the name.
        sanitized_name = re.sub(r"[\r\n]+", " ", name).strip()
        entry: SessionInfoEntry = {
            "type": "session_info",
            "id": generate_session_entry_id(self.by_id),
            "parentId": self.append_parent_id,
            "timestamp": _now_iso(),
            "name": sanitized_name,
        }
        self.append_entry(entry)
        return entry["id"]

    def append_custom_message_entry(
        self,
        custom_type: str,
        content: Union[str, list],
        display: bool,
        details: Optional[Any] = None,
    ) -> str:
        """Append a custom message entry. Mirrors
        ``appendCustomMessageEntry``
        (``session-manager-entries.ts:145-163``)."""
        entry: CustomMessageEntry = {
            "type": "custom_message",
            "customType": custom_type,
            "content": content,
            "display": display,
            "id": generate_session_entry_id(self.by_id),
            "parentId": self.append_parent_id,
            "timestamp": _now_iso(),
        }
        if details is not None:
            entry["details"] = details
        opts = type("AppendOpts", (), {
            "invalidate_serialized_prefix_cache": True,
        })()
        self.append_entry(entry, opts)
        return entry["id"]

    def append_label_change(
        self, target_id: str, label: Optional[str]
    ) -> str:
        """Append a label change entry. Mirrors
        ``appendLabelChange``
        (``session-manager-entries.ts:193-214``)."""
        if target_id not in self.by_id:
            raise RuntimeError(f"Entry {target_id} not found")
        entry: LabelEntry = {
            "type": "label",
            "id": generate_session_entry_id(self.by_id),
            "parentId": self.append_parent_id,
            "timestamp": _now_iso(),
            "targetId": target_id,
        }
        if label is not None:
            entry["label"] = label
        self.append_entry(entry)
        if label:
            self.labels_by_id[target_id] = label
            self.label_timestamps_by_id[target_id] = entry["timestamp"]
        else:
            self.labels_by_id.pop(target_id, None)
            self.label_timestamps_by_id.pop(target_id, None)
        return entry["id"]

    # ------------------------------------------------------------------
    # Getters
    # ------------------------------------------------------------------

    def get_leaf_id(self) -> Optional[str]:
        """Return the current leaf id. Mirrors
        ``getLeafId``
        (``session-manager-entries.ts:165-167``)."""
        return self.leaf_id

    def get_leaf_entry(self) -> Optional[SessionEntry]:
        """Return the current leaf entry. Mirrors
        ``getLeafEntry``
        (``session-manager-entries.ts:169-171``)."""
        if self.leaf_id is None:
            return None
        return self.get_entry(self.leaf_id)

    def get_entry(self, entry_id: str) -> Optional[SessionEntry]:
        """Return a single entry by id. Mirrors
        ``getEntry``
        (``session-manager-entries.ts:173-176``)."""
        entry = self.by_id.get(entry_id)
        return self.normalize_entry_parent(entry) if entry is not None else None

    def get_children(self, parent_id: str) -> list[SessionEntry]:
        """Return the direct children of
        ``parent_id``. Mirrors ``getChildren``
        (``session-manager-entries.ts:178-187``)."""
        children: list[SessionEntry] = []
        for entry in self.by_id.values():
            normalized = self.normalize_entry_parent(entry)
            if normalized.get("parentId") == parent_id:
                children.append(normalized)
        return children

    def get_label(self, entry_id: str) -> Optional[str]:
        """Return the label for an entry. Mirrors
        ``getLabel``
        (``session-manager-entries.ts:189-191``)."""
        return self.labels_by_id.get(entry_id)

    def get_branch(self, from_id: Optional[str] = None) -> list[SessionEntry]:
        """Return the branch path from ``from_id``
        (or the current leaf) back to the root.
        Mirrors ``getBranch``
        (``session-manager-entries.ts:216-233``)."""
        path: list[SessionEntry] = []
        seen: set[str] = set()
        current_id = from_id if from_id is not None else self.leaf_id
        while current_id and current_id not in seen:
            seen.add(current_id)
            current = self.by_id.get(current_id)
            if current is not None:
                normalized = self.normalize_entry_parent(current)
                path.append(normalized)
                current_id = normalized.get("parentId")
            else:
                current_id = self.opaque_parents_by_id.get(current_id)
        path.reverse()
        return path

    def get_header(self) -> Optional[SessionHeader]:
        """Return the session header. Mirrors
        ``getHeader``
        (``session-manager-entries.ts:239-241``)."""
        for entry in self.file_entries:
            if isinstance(entry, dict) and entry.get("type") == "session":
                return entry  # type: ignore[return-value]
        return None

    def get_entries(self) -> list[SessionEntry]:
        """Return every non-header entry with
        normalized parents. Mirrors ``getEntries``
        (``session-manager-entries.ts:243-247``)."""
        result: list[SessionEntry] = []
        for entry in self.file_entries:
            if not isinstance(entry, dict):
                continue
            if entry.get("type") == "session":
                continue
            if is_indexed_session_entry(entry):
                result.append(self.normalize_entry_parent(entry))
        return result

    def get_tree(self) -> list[SessionTreeNode]:
        """Return the tree of entries rooted at
        the leaves. Mirrors ``getTree``
        (``session-manager-entries.ts:249-285``)."""
        entries = self.get_entries()
        node_map: dict[str, SessionTreeNode] = {}
        for entry in entries:
            node_map[entry["id"]] = {
                "entry": entry,
                "children": [],
            }
            label = self.labels_by_id.get(entry["id"])
            if label is not None:
                node_map[entry["id"]]["label"] = label
            label_ts = self.label_timestamps_by_id.get(entry["id"])
            if label_ts is not None:
                node_map[entry["id"]]["labelTimestamp"] = label_ts
        roots: list[SessionTreeNode] = []
        for entry in entries:
            node = node_map[entry["id"]]
            parent_id = self.resolve_canonical_parent_id(entry.get("parentId"))
            if parent_id is None or parent_id == entry["id"]:
                roots.append(node)
                continue
            parent = node_map.get(parent_id)
            if parent is not None:
                parent["children"].append(node)
            else:
                roots.append(node)

        def _sort_recursive(node: SessionTreeNode) -> None:
            node["children"].sort(
                key=lambda n: _parse_iso_ms(n["entry"]["timestamp"])
            )
            for child in node["children"]:
                _sort_recursive(child)

        for root in roots:
            _sort_recursive(root)
        return roots

    def get_session_name(self) -> Optional[str]:
        """Return the most-recent
        ``session_info`` name. Mirrors
        ``getSessionName``
        (``session-manager-entries.ts:136-143``)."""
        for entry in reversed(self.get_entries()):
            if entry.get("type") == "session_info":
                name = entry.get("name")
                if isinstance(name, str):
                    stripped = name.strip()
                    if stripped:
                        return stripped
        return None

    def build_session_context(self) -> SessionContext:
        """Build a :class:`SessionContext` from
        the current branch. Mirrors
        ``buildSessionContext``
        (``session-manager-entries.ts:235-237``)."""
        return build_session_context(
            self.get_branch(),
            self.leaf_id,
            self.by_id,
        )

    # ------------------------------------------------------------------
    # Branch mutators
    # ------------------------------------------------------------------

    def branch(self, branch_from_id: str) -> None:
        """Switch the leaf to ``branch_from_id``.
        Mirrors ``branch``
        (``session-manager-entries.ts:287-295``)."""
        branch_target_id = self.resolve_branch_target_id(branch_from_id)
        if branch_target_id is None:
            raise RuntimeError(f"Entry {branch_from_id} not found")
        self.leaf_id = branch_target_id
        self.append_parent_id = branch_target_id
        self.prompt_released_side_branch_parent_id = None

    def reset_leaf(self) -> None:
        """Reset the leaf. Mirrors ``resetLeaf``
        (``session-manager-entries.ts:297-301``)."""
        self.leaf_id = None
        self.append_parent_id = None
        self.prompt_released_side_branch_parent_id = None

    def branch_with_summary(
        self,
        branch_from_id: Optional[str],
        summary: str,
        details: Optional[Any] = None,
        from_hook: Optional[bool] = None,
    ) -> str:
        """Switch the leaf + append a
        ``branch_summary`` entry. Mirrors
        ``branchWithSummary``
        (``session-manager-entries.ts:303-329``)."""
        branch_target_id = (
            None
            if branch_from_id is None
            else self.resolve_branch_target_id(branch_from_id)
        )
        if branch_from_id is not None and branch_target_id is None:
            raise RuntimeError(f"Entry {branch_from_id} not found")
        self.leaf_id = branch_target_id
        self.append_parent_id = branch_target_id
        entry: BranchSummaryEntry = {
            "type": "branch_summary",
            "id": generate_session_entry_id(self.by_id),
            "parentId": branch_target_id,
            "timestamp": _now_iso(),
            "fromId": branch_target_id if branch_target_id is not None else "root",
            "summary": summary,
        }
        if details is not None:
            entry["details"] = details
        if from_hook is not None:
            entry["fromHook"] = from_hook
        invalidate_cache = (from_hook is True) or (details is not None)
        opts: Any = None
        if invalidate_cache:
            opts = type("AppendOpts", (), {
                "invalidate_serialized_prefix_cache": True,
            })()
        self.append_entry(entry, opts)
        return entry["id"]


def _parse_iso_ms(iso_str: str) -> int:
    """Parse an ISO-8601 string into epoch ms.
    Used for ``getTree`` timestamp sort."""
    try:
        return int(
            datetime.fromisoformat(iso_str.replace("Z", "+00:00")).timestamp()
            * 1000
        )
    except (ValueError, TypeError):
        return 0


__all__ = [
    "SessionManagerEntries",
]
