"""jarvis.agents.sessions.session_manager — session manager facade.

OpenClaw parity: mirrors
``openclaw-main/src/agents/sessions/session-manager.ts``.

The public :class:`SessionManager` facade —
the entry point the brain (Layer 1's
``createAgentSession``) calls. Wraps
:class:`SessionManagerBranching` and adds
static factory methods (``create``,
``open``, ``continueRecent``, ``inMemory``,
``forkFrom``, ``list``, ``listAll``).

Phase 6.5 — session manager facade.

Adaptations
-----------
- The OpenClaw source uses a ``private
  constructor`` + static factories. The
  Python port uses a public ``__init__`` +
  static factories (the public init matches
  the inherited ``SessionManagerBranching``
  constructor).
- The OpenClaw source's
  ``loadTranscriptEventsSync(marker) as FileEntry[]``
  callback in ``SessionManager.open`` is a
  stub in 6.5 (Phase 6.5+ wires the full
  transcript-DB read; the file-only path
  remains functional via the file-loader
  fallback).
- The OpenClaw source's
  ``appendJsonlEntrySync`` /
  ``existsSync`` / ``mkdirSync`` /
  ``process.cwd()`` are replaced with the
  :mod:`os` + :func:`os.getcwd` Python
  equivalents.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional

from .session_manager_branching import SessionManagerBranching
from .session_manager_types import NewSessionOptions
from .session_manager_codec import (
    CURRENT_SESSION_VERSION,
    build_session_context,
    get_latest_compaction_entry,
    has_readable_session_header,
    is_json_record,
    migrate_session_entries,
    normalize_loaded_file_entry,
    parse_session_entries,
)
from .session_manager_file import (
    LoadedSessionFile,
    get_default_session_dir,
    load_entries_from_file,
    load_entries_from_file_with_snapshot,
    load_sqlite_marked_session_file,
    revalidate_loaded_session_file,
)
from .session_manager_id import create_session_id
from .session_manager_list import find_most_recent_session, list_all_sessions, list_sessions
from .session_manager_types import (
    AppendPersistenceOptions,
    BranchSummaryEntry,
    CompactionEntry,
    CustomEntry,
    CustomMessageEntry,
    FileEntry,
    LabelEntry,
    ModelChangeEntry,
    PromptReleasedSessionEntry,
    PromptReleasedSessionMergeResult,
    SessionContext,
    SessionEntry,
    SessionHeader,
    SessionInfo,
    SessionInfoEntry,
    SessionListProgress,
    SessionMessageEntry,
    SessionTreeNode,
    ThinkingLevelChangeEntry,
)


_LOG = logging.getLogger("jarvis.agents.sessions.session_manager")


def _now_iso() -> str:
    """Return the current UTC time as an ISO-8601
    string."""
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


# Re-export the public types from
# ``session-manager-types.ts`` and the codec
# helpers from ``session-manager-codec.ts``.
# The Python port uses a flat namespace here.
__all__ = [
    "CURRENT_SESSION_VERSION",
    "build_session_context",
    "find_most_recent_session",
    "get_default_session_dir",
    "get_latest_compaction_entry",
    "has_readable_session_header",
    "is_json_record",
    "list_all_sessions",
    "list_sessions",
    "load_entries_from_file",
    "migrate_session_entries",
    "normalize_loaded_file_entry",
    "parse_session_entries",
    # Public types
    "AppendPersistenceOptions",
    "BranchSummaryEntry",
    "CompactionEntry",
    "CustomEntry",
    "CustomMessageEntry",
    "FileEntry",
    "LabelEntry",
    "ModelChangeEntry",
    "NewSessionOptions",
    "PromptReleasedSessionEntry",
    "PromptReleasedSessionMergeResult",
    "ReadonlySessionManager",
    "SessionContext",
    "SessionEntry",
    "SessionHeader",
    "SessionInfo",
    "SessionInfoEntry",
    "SessionListProgress",
    "SessionManager",
    "SessionMessageEntry",
    "SessionTreeNode",
    "ThinkingLevelChangeEntry",
]


class SessionManager(SessionManagerBranching):
    """Public session-manager facade. Mirrors
    ``SessionManager``
    (``session-manager.ts:71-342``).

    Extends :class:`SessionManagerBranching`
    and adds the static factory methods
    (``create``, ``open``, ``continueRecent``,
    ``inMemory``, ``forkFrom``, ``list``,
    ``listAll``).
    """

    # The OpenClaw source's
    # ``private constructor`` becomes a
    # public ``__init__`` in Python (so the
    # static factories can call it). The
    # constructor signature matches
    # :class:`SessionManagerBranching`'s.

    # ------------------------------------------------------------------
    # Static factories
    # ------------------------------------------------------------------

    @staticmethod
    def create(
        cwd: str,
        session_dir: Optional[str] = None,
        sqlite_persistence: Optional[dict] = None,
        created_actor: Optional[str] = None,
        is_draft: bool = False,
    ) -> "SessionManager":
        """Create a new in-memory + on-disk
        session for ``cwd``. Mirrors
        ``SessionManager.create``
        (``session-manager.ts:256-259``)."""
        directory = session_dir or get_default_session_dir(cwd)
        return SessionManager(
            cwd=cwd,
            session_dir=directory,
            session_file=None,
            persist=True,
            sqlite_persistence=sqlite_persistence,
            new_session_options=NewSessionOptions(
                created_actor=created_actor,
                is_draft=is_draft,
            ),
        )

    @staticmethod
    def open(
        path: str,
        session_dir: Optional[str] = None,
        cwd_override: Optional[str] = None,
    ) -> "SessionManager":
        """Open an existing session file (or
        SQLite marker). Mirrors
        ``SessionManager.open``
        (``session-manager.ts:261-283``)."""
        sqlite_loaded = load_sqlite_marked_session_file(
            path,
            load_events=_sqlite_load_events_stub,
            options={"cwdOverride": cwd_override} if cwd_override else None,
        )
        if sqlite_loaded:
            return SessionManager(
                cwd=sqlite_loaded["cwd"],
                session_dir=session_dir or "",
                session_file=path,
                persist=True,
                loaded_session_file=LoadedSessionFile(
                    entries=sqlite_loaded["entries"], snapshot=None
                ),
                sqlite_persistence={
                    **sqlite_loaded["sqliteMarker"],
                    "session_key": sqlite_loaded["sessionKey"],
                },
            )
        loaded = revalidate_loaded_session_file(
            path, load_entries_from_file_with_snapshot(path)
        )
        header = next(
            (
                entry
                for entry in loaded.entries
                if isinstance(entry, dict) and entry.get("type") == "session"
            ),
            None,
        )
        cwd = (
            cwd_override
            or (header.get("cwd") if isinstance(header, dict) else None)
            or os.getcwd()
        )
        directory = session_dir or os.path.dirname(os.path.abspath(path))
        return SessionManager(
            cwd=cwd,
            session_dir=directory,
            session_file=path,
            persist=True,
            loaded_session_file=loaded,
        )

    @staticmethod
    def continue_recent(
        cwd: str, session_dir: Optional[str] = None
    ) -> "SessionManager":
        """Open the most-recent session for
        ``cwd`` (or create a new one if no
        recent session exists). Mirrors
        ``SessionManager.continueRecent``
        (``session-manager.ts:285-291``)."""
        directory = session_dir or get_default_session_dir(cwd)
        most_recent = find_most_recent_session(directory, cwd)
        if most_recent:
            return SessionManager(
                cwd=cwd,
                session_dir=directory,
                session_file=most_recent,
                persist=True,
            )
        return SessionManager(
            cwd=cwd,
            session_dir=directory,
            session_file=None,
            persist=True,
        )

    @staticmethod
    def in_memory(cwd: Optional[str] = None) -> "SessionManager":
        """Create an in-memory session manager
        (no persistence). Mirrors
        ``SessionManager.inMemory``
        (``session-manager.ts:293-295``)."""
        return SessionManager(
            cwd=cwd or os.getcwd(),
            session_dir="",
            session_file=None,
            persist=False,
        )

    @staticmethod
    def fork_from(
        source_path: str,
        target_cwd: str,
        session_dir: Optional[str] = None,
    ) -> "SessionManager":
        """Fork an existing session file into
        a new file. Mirrors
        ``SessionManager.forkFrom``
        (``session-manager.ts:297-329``)."""
        source_entries = load_entries_from_file(source_path)
        if not source_entries:
            raise RuntimeError(
                f"Cannot fork: source session file is empty or invalid: {source_path}"
            )
        if not any(
            isinstance(entry, dict) and entry.get("type") == "session"
            for entry in source_entries
        ):
            raise RuntimeError(
                f"Cannot fork: source session has no header: {source_path}"
            )

        directory = session_dir or get_default_session_dir(target_cwd)
        if not os.path.isdir(directory):
            os.makedirs(directory, exist_ok=True)
        new_session_id = create_session_id()
        timestamp = _now_iso()
        file_timestamp = timestamp.replace(":", "-").replace(".", "-")
        new_session_file = os.path.join(
            directory, f"{file_timestamp}_{new_session_id}.jsonl"
        )
        new_header: SessionHeader = {
            "type": "session",
            "version": CURRENT_SESSION_VERSION,
            "id": new_session_id,
            "timestamp": timestamp,
            "cwd": target_cwd,
            "parentSession": source_path,
        }
        # Write the new file (header + all
        # non-header source entries).
        with open(new_session_file, "w", encoding="utf-8") as f:
            f.write(_json_dumps(new_header) + "\n")
            for entry in source_entries:
                if isinstance(entry, dict) and entry.get("type") == "session":
                    continue
                f.write(_json_dumps(entry) + "\n")
        return SessionManager(
            cwd=target_cwd,
            session_dir=directory,
            session_file=new_session_file,
            persist=True,
        )

    @staticmethod
    async def list(
        cwd: str,
        session_dir: Optional[str] = None,
        on_progress: Optional[SessionListProgress] = None,
    ) -> list[SessionInfo]:
        """List the sessions for ``cwd``. Mirrors
        ``SessionManager.list``
        (``session-manager.ts:331-337``)."""
        return await list_sessions(
            cwd, session_dir or get_default_session_dir(cwd), on_progress
        )

    @staticmethod
    async def list_all(
        on_progress: Optional[SessionListProgress] = None,
    ) -> list[SessionInfo]:
        """List every session across all
        session sub-dirs. Mirrors
        ``SessionManager.listAll``
        (``session-manager.ts:339-341``)."""
        return await list_all_sessions(on_progress)


def _json_dumps(value: Any) -> str:
    """JSON-serialize a value with the canonical
    separators (no trailing whitespace)."""
    import json
    return json.dumps(value, ensure_ascii=False)


def _sqlite_load_events_stub(marker: dict) -> list[FileEntry]:
    from jarvis_state_core import load_agent_session_entries, open_agent_database

    handle = open_agent_database(
        {
            "agent_id": str(marker.get("agent_id", "")),
            "path": str(marker.get("store_path", "")),
        }
    )
    return load_agent_session_entries(handle, str(marker.get("session_id", "")))


# ----------------------------------------------------------------------------
# Public read-only type alias.
# ----------------------------------------------------------------------------


#: Mirrors ``ReadonlySessionManager``
#: (``session-manager.ts:344-358``). The
#: Python port uses a ``Protocol``-style
#: read-only view (callable + attribute
#: access) since the public methods are
#: already on the class.
class ReadonlySessionManager:
    """Read-only view of a
    :class:`SessionManager`. The Python port
    exposes this as the canonical
    ``SessionManager`` class itself (every
    method that mutates state is excluded
    by the caller's convention); the type
    alias is provided for OpenClaw parity."""

    def __init__(self, sm: "SessionManager") -> None:
        self._sm = sm

    def get_cwd(self) -> str:
        return self._sm.get_cwd()

    def get_session_dir(self) -> str:
        return self._sm.get_session_dir()

    def get_session_id(self) -> str:
        return self._sm.get_session_id()

    def get_session_file(self) -> Optional[str]:
        return self._sm.get_session_file()

    def get_leaf_id(self) -> Optional[str]:
        return self._sm.get_leaf_id()

    def get_leaf_entry(self) -> Optional[SessionEntry]:
        return self._sm.get_leaf_entry()

    def get_entry(self, entry_id: str) -> Optional[SessionEntry]:
        return self._sm.get_entry(entry_id)

    def get_label(self, entry_id: str) -> Optional[str]:
        return self._sm.get_label(entry_id)

    def get_branch(self, from_id: Optional[str] = None) -> list[SessionEntry]:
        return self._sm.get_branch(from_id)

    def get_header(self) -> Optional[SessionHeader]:
        return self._sm.get_header()

    def get_entries(self) -> list[SessionEntry]:
        return self._sm.get_entries()

    def get_tree(self) -> list[SessionTreeNode]:
        return self._sm.get_tree()

    def get_session_name(self) -> Optional[str]:
        return self._sm.get_session_name()
