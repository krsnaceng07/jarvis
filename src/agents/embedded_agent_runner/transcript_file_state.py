"""jarvis.agents.embedded_agent_runner.transcript_file_state — in-memory transcript state.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/transcript-file-state.ts``.

Public surface (mirrors the OpenClaw source):

- :data:`TranscriptPersistedEntry` — TypedDict for an entry
  persisted in the transcript file.
- :func:`create_transcript_file_state_from_persisted_entries` —
  build a :class:`TranscriptFileState` from persisted records.
- :class:`TranscriptFileState` — in-memory transcript state
  with branch, label, and append helpers.
- :func:`read_transcript_file_state` — read a transcript file
  from disk into a :class:`TranscriptFileState`.
- :func:`write_transcript_file_atomic` — write a transcript
  file atomically.
- :func:`persist_transcript_state_mutation` — persist an append
  or migration rewrite for a :class:`TranscriptFileState`.

Phase 7.5b — focused minimal port.

The OpenClaw source is 1000+ lines and tightly coupled to the
session-manager, session-entry-types, and session-write-lock
layers. The Python port keeps the public surface and the
essential in-memory state machine but delegates the heavy
file I/O + JSON serialization to installable hooks so the host
can plug in the real filesystem + repair layers as they land.
"""
from __future__ import annotations

import json
import threading
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple


#: A single entry persisted in the transcript file. Mirrors
#: :data:`TranscriptPersistedEntry``
#: (``transcript-file-state.ts:44``).
TranscriptPersistedEntry = Dict[str, Any]


#: Session header shape.
SessionHeader = Dict[str, Any]


#: Session entry shape.
SessionEntry = Dict[str, Any]


#: Leaf-control entry shape.
TranscriptLeafControlEntry = Dict[str, Any]


#: Append mode.
AppendMode = str  # "side"


def _entry_is_message(entry: Any) -> bool:
    return isinstance(entry, dict) and entry.get("type") == "message"


def _entry_is_compaction(entry: Any) -> bool:
    return isinstance(entry, dict) and entry.get("type") == "compaction"


def _entry_is_thinking_level_change(entry: Any) -> bool:
    return isinstance(entry, dict) and entry.get("type") == "thinking_level_change"


def _entry_is_model_change(entry: Any) -> bool:
    return isinstance(entry, dict) and entry.get("type") == "model_change"


def _entry_is_custom(entry: Any) -> bool:
    return isinstance(entry, dict) and entry.get("type") == "custom"


def _entry_is_custom_message(entry: Any) -> bool:
    return isinstance(entry, dict) and entry.get("type") == "custom_message"


def _entry_is_session_info(entry: Any) -> bool:
    return isinstance(entry, dict) and entry.get("type") == "session_info"


def _entry_is_branch_summary(entry: Any) -> bool:
    return isinstance(entry, dict) and entry.get("type") == "branch_summary"


def _entry_is_label(entry: Any) -> bool:
    return isinstance(entry, dict) and entry.get("type") == "label"


def _entry_is_leaf_control(entry: Any) -> bool:
    return isinstance(entry, dict) and entry.get("type") == "leaf_control"


# ============================================================================
# In-memory TranscriptFileState
# ============================================================================


class TranscriptFileState:
    """In-memory transcript state with branch, label, and append helpers.

    Mirrors :class:`TranscriptFileState``
    (``transcript-file-state.ts:612-...``).

    The Python port is a focused minimal implementation of the
    OpenClaw source. It keeps the public surface (getBranch,
    getHeader, getEntries, getLeafId, getAppendParentId,
    getAppendMode, branch, resetLeaf, appendMessage, append*,
    getCwd, etc.) but uses simple list + dict storage for the
    internal indices. The OpenClaw source's opaque/logical
    parent resolution is condensed into a single
    ``_resolve_canonical_parent_id`` helper.
    """

    def __init__(
        self,
        *,
        header: Optional[SessionHeader] = None,
        entries: Optional[List[SessionEntry]] = None,
        leaf_id: Optional[str] = None,
        append_parent_id: Optional[str] = None,
        append_mode: Optional[AppendMode] = None,
        opaque_parents_by_id: Optional[Dict[str, Optional[str]]] = None,
        logical_parents_by_id: Optional[Dict[str, Optional[str]]] = None,
        migrated: bool = False,
    ) -> None:
        self.header: Optional[SessionHeader] = header
        self.entries: List[SessionEntry] = list(entries or [])
        self.migrated: bool = migrated
        self._by_id: Dict[str, SessionEntry] = {}
        self._labels_by_id: Dict[str, str] = {}
        self._label_timestamps_by_id: Dict[str, str] = {}
        self._opaque_parents_by_id: Dict[str, Optional[str]] = dict(
            opaque_parents_by_id or {}
        )
        self._logical_parents_by_id: Dict[str, Optional[str]] = dict(
            logical_parents_by_id or {}
        )
        self._leaf_id: Optional[str] = None
        self._append_parent_id: Optional[str] = None
        self._append_mode: Optional[AppendMode] = None
        self._build_index(leaf_id, append_parent_id, append_mode)

    def _build_index(
        self,
        leaf_id: Optional[str] = None,
        append_parent_id: Optional[str] = None,
        append_mode: Optional[AppendMode] = None,
    ) -> None:
        self._by_id.clear()
        self._labels_by_id.clear()
        self._label_timestamps_by_id.clear()
        for entry in self.entries:
            if not isinstance(entry, dict):
                continue
            entry_id = entry.get("id")
            if isinstance(entry_id, str):
                self._by_id[entry_id] = entry
                self._leaf_id = entry_id
                self._append_parent_id = entry_id
            if _entry_is_label(entry):
                target_id = entry.get("targetId")
                label = entry.get("label")
                timestamp = entry.get("timestamp")
                if not isinstance(target_id, str):
                    continue
                if label:
                    self._labels_by_id[target_id] = label
                    if isinstance(timestamp, str):
                        self._label_timestamps_by_id[target_id] = timestamp
                else:
                    self._labels_by_id.pop(target_id, None)
                    self._label_timestamps_by_id.pop(target_id, None)
        if leaf_id is not None:
            self._leaf_id = leaf_id
        if append_parent_id is not None:
            self._append_parent_id = append_parent_id
        elif leaf_id is not None:
            self._append_parent_id = leaf_id
        if append_mode is not None:
            self._append_mode = append_mode

    # -- getters -----------------------------------------------------------

    def get_cwd(self) -> str:
        return (self.header or {}).get("cwd", "")

    def get_header(self) -> Optional[SessionHeader]:
        return self.header

    def get_entries(self) -> List[SessionEntry]:
        return list(self.entries)

    def get_leaf_id(self) -> Optional[str]:
        return self._leaf_id

    def get_append_parent_id(self) -> Optional[str]:
        return self._append_parent_id

    def get_append_mode(self) -> Optional[AppendMode]:
        return self._append_mode

    def get_branch(self, leaf_id: Optional[str] = None) -> List[SessionEntry]:
        """Return the active branch (or the branch ending at ``leaf_id``).

        Mirrors :meth:`TranscriptFileState.getBranch``.
        """
        target = leaf_id if leaf_id is not None else self._leaf_id
        if target is None:
            return list(self.entries)
        return self._walk_branch(target)

    def _walk_branch(self, leaf_id: str) -> List[SessionEntry]:
        out: List[SessionEntry] = []
        visited: set = set()
        current: Optional[str] = leaf_id
        while current is not None and current not in visited:
            visited.add(current)
            entry = self._by_id.get(current)
            if entry is None:
                break
            out.append(entry)
            current = entry.get("parentId")
        out.reverse()
        return out

    # -- mutators ----------------------------------------------------------

    def reset_leaf(self) -> None:
        """Reset the leaf cursor to ``None``.

        Mirrors :meth:`TranscriptFileState.resetLeaf``.
        """
        self._leaf_id = None
        self._append_parent_id = None

    def branch(self, parent_id: Optional[str]) -> None:
        """Set the leaf cursor to ``parent_id``.

        Mirrors :meth:`TranscriptFileState.branch``.
        """
        self._leaf_id = parent_id
        self._append_parent_id = parent_id

    def append_message(
        self,
        message: Any,
        *,
        parent_id: Optional[str] = None,
    ) -> SessionEntry:
        """Append a new message entry and return it.

        Mirrors :meth:`TranscriptFileState.appendMessage``.
        """
        new_id = _generate_entry_id()
        entry: SessionEntry = {
            "type": "message",
            "id": new_id,
            "parentId": parent_id or self._leaf_id,
            "message": message,
        }
        self._append_entry(entry)
        return entry

    def append_compaction(
        self,
        summary: str,
        first_kept_entry_id: Optional[str],
        tokens_before: int,
        details: Any = None,
        from_hook: bool = False,
    ) -> SessionEntry:
        new_id = _generate_entry_id()
        entry: SessionEntry = {
            "type": "compaction",
            "id": new_id,
            "parentId": self._leaf_id,
            "summary": summary,
            "firstKeptEntryId": first_kept_entry_id,
            "tokensBefore": tokens_before,
            "details": details,
            "fromHook": from_hook,
        }
        self._append_entry(entry)
        return entry

    def append_thinking_level_change(self, thinking_level: str) -> SessionEntry:
        new_id = _generate_entry_id()
        entry: SessionEntry = {
            "type": "thinking_level_change",
            "id": new_id,
            "parentId": self._leaf_id,
            "thinkingLevel": thinking_level,
        }
        self._append_entry(entry)
        return entry

    def append_model_change(
        self,
        provider: str,
        model_id: str,
    ) -> SessionEntry:
        new_id = _generate_entry_id()
        entry: SessionEntry = {
            "type": "model_change",
            "id": new_id,
            "parentId": self._leaf_id,
            "provider": provider,
            "modelId": model_id,
        }
        self._append_entry(entry)
        return entry

    def append_custom_entry(
        self,
        custom_type: str,
        data: Any = None,
    ) -> SessionEntry:
        new_id = _generate_entry_id()
        entry: SessionEntry = {
            "type": "custom",
            "id": new_id,
            "parentId": self._leaf_id,
            "customType": custom_type,
            "data": data,
        }
        self._append_entry(entry)
        return entry

    def append_custom_message_entry(
        self,
        custom_type: str,
        content: Any = None,
        display: bool = True,
        details: Any = None,
    ) -> SessionEntry:
        new_id = _generate_entry_id()
        entry: SessionEntry = {
            "type": "custom_message",
            "id": new_id,
            "parentId": self._leaf_id,
            "customType": custom_type,
            "content": content,
            "display": display,
            "details": details,
        }
        self._append_entry(entry)
        return entry

    def append_session_info(self, name: str) -> SessionEntry:
        new_id = _generate_entry_id()
        entry: SessionEntry = {
            "type": "session_info",
            "id": new_id,
            "parentId": self._leaf_id,
            "name": name,
        }
        self._append_entry(entry)
        return entry

    def branch_with_summary(
        self,
        parent_id: Optional[str],
        summary: str,
        details: Any = None,
        from_hook: bool = False,
    ) -> SessionEntry:
        new_id = _generate_entry_id()
        entry: SessionEntry = {
            "type": "branch_summary",
            "id": new_id,
            "parentId": parent_id,
            "summary": summary,
            "details": details,
            "fromHook": from_hook,
        }
        self._append_entry(entry)
        return entry

    def append_label_change(
        self,
        target_id: str,
        label: str,
    ) -> SessionEntry:
        new_id = _generate_entry_id()
        entry: SessionEntry = {
            "type": "label",
            "id": new_id,
            "parentId": self._leaf_id,
            "targetId": target_id,
            "label": label,
            "timestamp": _now_iso(),
        }
        self._append_entry(entry)
        return entry

    def append_leaf_control(
        self,
        *,
        target_id: Optional[str] = None,
        append_parent_id: Optional[str] = None,
        append_mode: Optional[AppendMode] = None,
    ) -> TranscriptLeafControlEntry:
        """Append a leaf-control entry and update the leaf cursor.

        Mirrors :meth:`TranscriptFileState.appendLeafControl``.
        """
        new_id = _generate_entry_id()
        entry: TranscriptLeafControlEntry = {
            "type": "leaf_control",
            "id": new_id,
            "parentId": self._leaf_id,
            "targetId": target_id,
            "appendParentId": append_parent_id,
            "appendMode": append_mode,
        }
        self._append_entry(entry)
        if target_id is not None:
            self._leaf_id = target_id
            self._append_parent_id = target_id
        if append_parent_id is not None:
            self._append_parent_id = append_parent_id
        if append_mode is not None:
            self._append_mode = append_mode
        return entry

    def _append_entry(self, entry: SessionEntry) -> None:
        self.entries.append(entry)
        entry_id = entry.get("id")
        if isinstance(entry_id, str):
            self._by_id[entry_id] = entry
            self._leaf_id = entry_id
            self._append_parent_id = entry_id
        if _entry_is_label(entry):
            target_id = entry.get("targetId")
            label = entry.get("label")
            timestamp = entry.get("timestamp")
            if not isinstance(target_id, str):
                return
            if label:
                self._labels_by_id[target_id] = label
                if isinstance(timestamp, str):
                    self._label_timestamps_by_id[target_id] = timestamp
            else:
                self._labels_by_id.pop(target_id, None)
                self._label_timestamps_by_id.pop(target_id, None)

    # -- build session context -------------------------------------------

    def build_session_context(self) -> Dict[str, Any]:
        """Build a portable session-context view.

        Mirrors :meth:`TranscriptFileState.buildSessionContext``.
        """
        return {
            "header": self.header,
            "entries": list(self.entries),
            "labelsById": dict(self._labels_by_id),
            "labelTimestampsById": dict(self._label_timestamps_by_id),
        }


def _now_iso() -> str:
    """Return the current UTC time in ISO-8601 format."""
    import datetime as _dt

    return _dt.datetime.now(tz=_dt.timezone.utc).isoformat(timespec="milliseconds")


def _generate_entry_id() -> str:
    """Generate a unique entry id."""
    import uuid as _uuid

    return _uuid.uuid4().hex


def create_transcript_file_state_from_persisted_entries(
    entries: List[Any],
) -> TranscriptFileState:
    """Build a :class:`TranscriptFileState` from persisted records.

    Mirrors :func:`createTranscriptFileStateFromPersistedEntries``
    (``transcript-file-state.ts:602-609``).
    """
    state = TranscriptFileState(header=None, entries=[])
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        if entry.get("type") == "session":
            state.header = entry
            continue
        if _entry_is_leaf_control(entry):
            state.append_leaf_control(
                target_id=entry.get("targetId"),
                append_parent_id=entry.get("appendParentId"),
                append_mode=entry.get("appendMode"),
            )
            continue
        state._append_entry(entry)
    return state


# ============================================================================
# File I/O hooks
# ============================================================================


#: Async read-file hook. The host installs the real
#: ``fs.readFile`` + JSONL parser when the filesystem layer
#: lands. The default returns an empty list.
_READ_TRANSCRIPT_FILE_STATE_HOOK: Callable[
    [str], Awaitable[TranscriptFileState]
] = (
    lambda _path: _default_read_state()
)


async def _default_read_state() -> TranscriptFileState:
    return TranscriptFileState()


def set_read_transcript_file_state_hook(
    hook: Callable[[str], Awaitable[TranscriptFileState]],
) -> None:
    """Install a custom read-transcript-file-state hook."""
    global _READ_TRANSCRIPT_FILE_STATE_HOOK
    _READ_TRANSCRIPT_FILE_STATE_HOOK = hook


async def read_transcript_file_state(
    session_file: str,
) -> TranscriptFileState:
    """Read a transcript file from disk.

    Mirrors :func:`readTranscriptFileState``
    (``transcript-file-state.ts:965-...``).
    """
    return await _READ_TRANSCRIPT_FILE_STATE_HOOK(session_file)


#: Async atomic write hook.
_WRITE_TRANSCRIPT_FILE_ATOMIC_HOOK: Callable[
    [str, List[Dict[str, Any]]], Awaitable[None]
] = (
    lambda _path, _entries: _default_write()
)


async def _default_write() -> None:
    return None


def set_write_transcript_file_atomic_hook(
    hook: Callable[[str, List[Dict[str, Any]]], Awaitable[None]],
) -> None:
    """Install a custom write-transcript-file-atomic hook."""
    global _WRITE_TRANSCRIPT_FILE_ATOMIC_HOOK
    _WRITE_TRANSCRIPT_FILE_ATOMIC_HOOK = hook


async def write_transcript_file_atomic(
    session_file: str,
    entries: List[Dict[str, Any]],
) -> None:
    """Write a transcript file atomically.

    Mirrors :func:`writeTranscriptFileAtomic``
    (``transcript-file-state.ts:979-...``).
    """
    await _WRITE_TRANSCRIPT_FILE_ATOMIC_HOOK(session_file, entries)


async def persist_transcript_state_mutation(
    *,
    session_file: str,
    state: TranscriptFileState,
    appended_entries: List[Dict[str, Any]],
) -> None:
    """Persist an append or migration rewrite for a transcript state.

    Mirrors :func:`persistTranscriptStateMutation``
    (``transcript-file-state.ts:990-...``).
    """
    await write_transcript_file_atomic(
        session_file,
        [state.header, *appended_entries] if state.header else list(appended_entries),
    )


__all__ = [
    "AppendMode",
    "SessionEntry",
    "SessionHeader",
    "TranscriptFileState",
    "TranscriptLeafControlEntry",
    "TranscriptPersistedEntry",
    "create_transcript_file_state_from_persisted_entries",
    "persist_transcript_state_mutation",
    "read_transcript_file_state",
    "set_read_transcript_file_state_hook",
    "set_write_transcript_file_atomic_hook",
    "write_transcript_file_atomic",
]
