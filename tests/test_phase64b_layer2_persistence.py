"""Phase 6.4b — Layer 2 session persistence.

Tests for
:class:`jarvis.agents.sessions.session_manager_persistence.SessionManagerPersistence`.

- ``persist`` writes the first-ever assistant
  message via the full-file path
- Subsequent persists use the file-append
  path
- The cache is updated after the persist
- ``remove_trailing_entries`` drops matching
  tail entries + parent-id re-resolution
- ``remove_trailing_entries`` with
  ``preserve_trailing`` keeps the optional
  matches
- ``sync_snapshot_after_header_rewrite``
  updates the snapshot
- ``merge_prompt_released_session_entries``
  merges side-branch entries
"""
from __future__ import annotations

import json
import os
import sys

import pytest

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_THIS_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from src.agents.sessions import (  # noqa: E402
    CURRENT_SESSION_VERSION,
    SessionManagerCore,
    SessionManagerPersistence,
    SessionMessageEntry,
)


# ── Helpers ─────────────────────────────────────────────────────


def _v3_header(cwd: str = "/some/cwd", sid: str = "s1") -> dict:
    return {
        "type": "session",
        "version": CURRENT_SESSION_VERSION,
        "id": sid,
        "timestamp": "2026-01-01T00:00:00.000Z",
        "cwd": cwd,
    }


def _v3_message(
    msg_id: str,
    role: str = "user",
    parent_id: object = None,
    content: str = "hi",
) -> SessionMessageEntry:
    return {
        "type": "message",
        "id": msg_id,
        "parentId": parent_id,
        "timestamp": "2026-01-01T00:00:00.000Z",
        "message": {"role": role, "content": content},
    }


def _write_session_file(file_path: str, header: dict, *entries: dict) -> None:
    lines = [json.dumps(header)] + [json.dumps(e) for e in entries]
    with open(file_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


# ── persist: first assistant message ─────────────────────────


def _add_message_to_state(
    sm: SessionManagerPersistence, msg: SessionMessageEntry
) -> None:
    """Mimic what :meth:`SessionManagerEntries.append_entry`
    does before calling :meth:`persist`: add the
    entry to ``file_entries`` + update the
    indexes."""
    sm.file_entries.append(msg)
    sm.by_id[msg["id"]] = msg
    sm.leaf_id = msg["id"]
    sm.append_parent_id = msg["id"]


class TestPersist:
    def test_first_user_message_no_flush(self, tmp_path) -> None:
        """The first user message is not flushed
        to disk (the OpenClaw source's
        ``hasAssistant`` short-circuit)."""
        sm = SessionManagerPersistence(
            cwd="/some/cwd",
            session_dir=str(tmp_path),
            session_file=str(tmp_path / "session.jsonl"),
            persist=True,
        )
        # No assistant message yet.
        msg = _v3_message("m1", role="user", parent_id=None)
        _add_message_to_state(sm, msg)
        sm.persist(msg)
        # The file is not flushed (no assistant
        # message → no full-file write).
        assert sm.flushed is False
        # The file does not exist yet (no full-
        # file write happened).
        assert not os.path.exists(str(tmp_path / "session.jsonl"))

    def test_first_assistant_message_writes_full_file(
        self, tmp_path
    ) -> None:
        """The first assistant message triggers
        a full-file write."""
        file_path = str(tmp_path / "session.jsonl")
        sm = SessionManagerPersistence(
            cwd="/some/cwd",
            session_dir=str(tmp_path),
            session_file=file_path,
            persist=True,
        )
        # Add a user message first (no flush).
        m1 = _v3_message("m1", role="user", parent_id=None)
        _add_message_to_state(sm, m1)
        sm.persist(m1)
        assert not os.path.exists(file_path)
        # Add an assistant message (flushes).
        m2 = _v3_message(
            "m2", role="assistant", parent_id="m1", content="hello"
        )
        _add_message_to_state(sm, m2)
        sm.persist(m2)
        # The full file is on disk.
        assert os.path.exists(file_path)
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        # The session header is in the file.
        assert "session" in content
        # Both messages are in the file.
        assert "m1" in content
        assert "m2" in content
        assert sm.flushed is True

    def test_subsequent_persist_uses_append(self, tmp_path) -> None:
        """Subsequent persists use the file-append
        path (not a full-file rewrite)."""
        file_path = str(tmp_path / "session.jsonl")
        sm = SessionManagerPersistence(
            cwd="/some/cwd",
            session_dir=str(tmp_path),
            session_file=file_path,
            persist=True,
        )
        # First flush.
        m1 = _v3_message("m1", role="user", parent_id=None)
        _add_message_to_state(sm, m1)
        sm.persist(m1)
        m2 = _v3_message("m2", role="assistant", parent_id="m1")
        _add_message_to_state(sm, m2)
        sm.persist(m2)
        # Capture the file size after the first
        # assistant message.
        size_after_first = os.path.getsize(file_path)
        # Append a second assistant message.
        m3 = _v3_message("m3", role="assistant", parent_id="m2")
        _add_message_to_state(sm, m3)
        sm.persist(m3)
        # The file grew (appended, not rewritten).
        assert os.path.getsize(file_path) > size_after_first
        # The new message is in the file.
        with open(file_path, "r", encoding="utf-8") as f:
            assert "m3" in f.read()

    def test_persist_does_nothing_when_not_persisted(
        self, tmp_path
    ) -> None:
        """``persist=False`` → no IO, no error."""
        sm = SessionManagerPersistence(
            cwd="/some/cwd",
            session_dir=str(tmp_path),
            session_file=None,
            persist=False,
        )
        m1 = _v3_message("m1", role="assistant")
        _add_message_to_state(sm, m1)
        sm.persist(m1)
        # No file was created.
        assert sm.session_file is None


# ── removeTrailingEntries ────────────────────────────────────


class TestRemoveTrailingEntries:
    def test_removes_matching_trailing_entries(self, tmp_path) -> None:
        """``remove_trailing_entries`` drops the
        trailing entries that match the
        predicate."""
        file_path = str(tmp_path / "session.jsonl")
        # Header + m1 (user) + m2 (assistant).
        sm = SessionManagerPersistence(
            cwd="/some/cwd",
            session_dir=str(tmp_path),
            session_file=file_path,
            persist=True,
        )
        m1 = _v3_message("m1", role="user", parent_id=None)
        _add_message_to_state(sm, m1)
        sm.persist(m1)
        m2 = _v3_message("m2", role="assistant", parent_id="m1")
        _add_message_to_state(sm, m2)
        sm.persist(m2)
        # Remove trailing entries matching role
        # == "assistant". Only m2 matches.
        removed = sm.remove_trailing_entries(
            lambda entry: entry.get("message", {}).get("role") == "assistant"
        )
        assert removed == 1
        # The file is rewritten.
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        assert "m1" in content
        assert "m2" not in content

    def test_preserves_preserved_trailing_entries(self, tmp_path) -> None:
        """``preserve_trailing`` keeps the matching
        entries before the predicate-matched
        entries."""
        file_path = str(tmp_path / "session.jsonl")
        sm = SessionManagerPersistence(
            cwd="/some/cwd",
            session_dir=str(tmp_path),
            session_file=file_path,
            persist=True,
        )
        m1 = _v3_message("m1", role="user", parent_id=None)
        _add_message_to_state(sm, m1)
        sm.persist(m1)
        m2 = _v3_message("m2", role="assistant", parent_id="m1")
        _add_message_to_state(sm, m2)
        sm.persist(m2)
        m3 = _v3_message("m3", role="assistant", parent_id="m2")
        _add_message_to_state(sm, m3)
        sm.persist(m3)
        m4 = _v3_message("m4", role="assistant", parent_id="m3")
        _add_message_to_state(sm, m4)
        sm.persist(m4)
        # Remove trailing entries matching role
        # == "assistant", but preserve the
        # last one (m4).
        removed = sm.remove_trailing_entries(
            lambda entry: entry.get("message", {}).get("role") == "assistant",
            options={
                "preserveTrailing": lambda entry: entry.get("id") == "m4"
            },
        )
        # Only m2 + m3 are removed (m4 is preserved).
        assert removed == 2
        # m4 is still in the file.
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        assert "m4" in content
        assert "m2" not in content
        assert "m3" not in content

    def test_removes_nothing_when_no_match(self, tmp_path) -> None:
        """``remove_trailing_entries`` returns 0
        when no entry matches."""
        file_path = str(tmp_path / "session.jsonl")
        sm = SessionManagerPersistence(
            cwd="/some/cwd",
            session_dir=str(tmp_path),
            session_file=file_path,
            persist=True,
        )
        m1 = _v3_message("m1", role="user", parent_id=None)
        _add_message_to_state(sm, m1)
        sm.persist(m1)
        m2 = _v3_message("m2", role="assistant", parent_id="m1")
        _add_message_to_state(sm, m2)
        sm.persist(m2)
        removed = sm.remove_trailing_entries(
            lambda entry: entry.get("id") == "nonexistent"
        )
        assert removed == 0


# ── syncSnapshotAfterHeaderRewrite ───────────────────────────


class TestSyncSnapshotAfterHeaderRewrite:
    def test_syncs_snapshot(self, tmp_path) -> None:
        """``sync_snapshot_after_header_rewrite``
        reads the current snapshot and caches
        it."""
        file_path = str(tmp_path / "session.jsonl")
        sm = SessionManagerPersistence(
            cwd="/some/cwd",
            session_dir=str(tmp_path),
            session_file=file_path,
            persist=True,
        )
        m1 = _v3_message("m1", role="user", parent_id=None)
        _add_message_to_state(sm, m1)
        sm.persist(m1)
        m2 = _v3_message("m2", role="assistant", parent_id="m1")
        _add_message_to_state(sm, m2)
        sm.persist(m2)
        # Clear the snapshot.
        sm.session_file_snapshot = None
        # Sync.
        sm.sync_snapshot_after_header_rewrite()
        # The snapshot is now set.
        assert sm.session_file_snapshot is not None


# ── mergePromptReleasedSessionEntries ────────────────────────


class TestMergePromptReleasedSessionEntries:
    def test_merges_side_branch_entries(self, tmp_path) -> None:
        """A batch of side-branch entries is
        merged into the file-entries. The
        ``persistLeaf=True`` path triggers a
        full rewrite that re-loads the file
        from disk; the result is the published
        snapshot + leaf control id."""
        file_path = str(tmp_path / "session.jsonl")
        sm = SessionManagerPersistence(
            cwd="/some/cwd",
            session_dir=str(tmp_path),
            session_file=file_path,
            persist=True,
        )
        m1 = _v3_message("m1", role="user", parent_id=None)
        _add_message_to_state(sm, m1)
        sm.persist(m1)
        m2 = _v3_message("m2", role="assistant", parent_id="m1")
        _add_message_to_state(sm, m2)
        sm.persist(m2)
        # Now merge a side-branch entry. The
        # entry has no ``preserveActiveLeaf``
        # (so it's a normal side-branch
        # append).
        side_entry: dict = {
            "type": "message",
            "id": "m3",
            "parentId": None,
            "timestamp": "2026-01-01T00:00:00.000Z",
            "message": {"role": "user", "content": "side"},
        }
        result = sm.merge_prompt_released_session_entries(
            [side_entry], options={"persistLeaf": True}
        )
        # The merge produced a result with a
        # published leaf control.
        assert result is not None
        assert "publishedEntries" in result
        # The session-file snapshot is set.
        assert sm.session_file_snapshot is not None
        # The file on disk was updated.
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        # The session header is in the file.
        assert "session" in content

    def test_no_persist_when_persist_leaf_false(self, tmp_path) -> None:
        """``persistLeaf=False`` → no leaf control
        is added (the entries are merged in
        memory only)."""
        file_path = str(tmp_path / "session.jsonl")
        sm = SessionManagerPersistence(
            cwd="/some/cwd",
            session_dir=str(tmp_path),
            session_file=file_path,
            persist=True,
        )
        m1 = _v3_message("m1", role="user", parent_id=None)
        _add_message_to_state(sm, m1)
        sm.persist(m1)
        m2 = _v3_message("m2", role="assistant", parent_id="m1")
        _add_message_to_state(sm, m2)
        sm.persist(m2)
        # No ``persistLeaf``.
        side_entry: dict = {
            "type": "message",
            "id": "m3",
            "parentId": None,
            "timestamp": "2026-01-01T00:00:00.000Z",
            "message": {"role": "user", "content": "side"},
        }
        result = sm.merge_prompt_released_session_entries([side_entry])
        # No leaf was persisted.
        assert result is None


# ── InMemory persistence ─────────────────────────────────────


class TestInMemoryPersistence:
    def test_in_memory_persist(self, tmp_path) -> None:
        """``persist=False`` → the persist path
        is a no-op (no file IO)."""
        sm = SessionManagerPersistence(
            cwd="/some/cwd",
            session_dir=str(tmp_path / "sessions"),
            session_file=None,
            persist=False,
        )
        m1 = _v3_message("m1", role="assistant")
        _add_message_to_state(sm, m1)
        sm.persist(m1)
        # No file was created.
        assert sm.get_session_file() is None


# ── Constructor with file ────────────────────────────────────


class TestPersistenceConstructor:
    def test_loads_existing_v3_file(self, tmp_path) -> None:
        """An existing v3 file is loaded."""
        file_path = str(tmp_path / "session.jsonl")
        _write_session_file(
            file_path,
            _v3_header(),
            _v3_message("m1", role="user", parent_id=None),
            _v3_message(
                "m2", role="assistant", parent_id="m1", content="hi"
            ),
        )
        sm = SessionManagerPersistence(
            cwd="/some/cwd",
            session_dir=str(tmp_path),
            session_file=file_path,
            persist=True,
        )
        # The session is loaded.
        assert sm.get_session_id() == "s1"
        assert sm.leaf_id == "m2"
        assert "m1" in sm.by_id
        assert "m2" in sm.by_id


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
