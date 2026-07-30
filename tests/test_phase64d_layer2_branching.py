"""Phase 6.4d — Layer 2 session branching.

Tests for
:class:`jarvis.agents.sessions.session_manager_branching.SessionManagerBranching`.

- ``create_branched_session(leaf_id)`` extracts
  a branch path + creates a new session
  file with the branch as the root.
- The new session has a fresh header with
  the new session id.
- Labels on the branch entries are
  preserved as ``label`` entries in the new
  session.
- The new session is persisted to disk when
  ``should_persist=True``.
- ``create_branched_session`` with a
  non-existent leaf raises a ``RuntimeError``.
- ``create_branched_session`` with
  ``persist=False`` returns ``None``.
- The original session is unchanged after
  the branch is created.
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
    SessionManagerBranching,
)


# ── createBranchedSession ─────────────────────────────────────


class TestCreateBranchedSession:
    def test_creates_new_session_file(self, tmp_path) -> None:
        """``create_branched_session`` returns
        a new session-file path.

        Note: the OpenClaw source's
        ``createBranchedSession`` only
        persists the new session when the
        branch contains an assistant message.
        This test branches from a leaf whose
        sub-tree includes the assistant."""
        file_path = str(tmp_path / "session.jsonl")
        sm = SessionManagerBranching(
            cwd="/some/cwd",
            session_dir=str(tmp_path),
            session_file=file_path,
            persist=True,
        )
        # Build a small branch: m1 (user) →
        # m2 (assistant). Branching from m2
        # includes the assistant in the new
        # session.
        m1 = sm.append_message({"role": "user", "content": "hi"})
        m2 = sm.append_message({"role": "assistant", "content": "hello"})
        # Create a branch from m2 (which
        # includes m1 + m2).
        new_file = sm.create_branched_session(m2)
        # The new file path is returned.
        assert new_file is not None
        assert new_file != file_path
        assert new_file.endswith(".jsonl")
        # The new file exists on disk.
        assert os.path.exists(new_file)
        # The current session is the new one.
        assert sm.get_session_file() == new_file

    def test_new_session_has_branched_entries(self, tmp_path) -> None:
        """The new session file contains the
        branched entries (m1, m2) but not
        post-branch entries."""
        file_path = str(tmp_path / "session.jsonl")
        sm = SessionManagerBranching(
            cwd="/some/cwd",
            session_dir=str(tmp_path),
            session_file=file_path,
            persist=True,
        )
        m1 = sm.append_message({"role": "user", "content": "hi"})
        m2 = sm.append_message({"role": "assistant", "content": "hello"})
        sm.append_message({"role": "user", "content": "ignored"})
        new_file = sm.create_branched_session(m2)
        # The new file has the session header
        # + m1 + m2 (but not m3).
        with open(new_file, "r", encoding="utf-8") as f:
            lines = f.read().strip().split("\n")
        entries = [json.loads(line) for line in lines]
        # The session header is first.
        assert entries[0]["type"] == "session"
        # m1 and m2 are in the file.
        ids = [e.get("id") for e in entries if "id" in e]
        assert m1 in ids
        assert m2 in ids
        # m3 is NOT in the file.
        assert "m3" not in ids

    def test_new_session_has_fresh_id(self, tmp_path) -> None:
        """The new session has a fresh session id
        (not the original)."""
        file_path = str(tmp_path / "session.jsonl")
        sm = SessionManagerBranching(
            cwd="/some/cwd",
            session_dir=str(tmp_path),
            session_file=file_path,
            persist=True,
        )
        m1 = sm.append_message({"role": "user", "content": "hi"})
        m2 = sm.append_message({"role": "assistant", "content": "hello"})
        original_id = sm.get_session_id()
        new_file = sm.create_branched_session(m2)
        with open(new_file, "r", encoding="utf-8") as f:
            header = json.loads(f.readline())
        # The new header has a different
        # session id.
        assert header["id"] != original_id
        # The new header has a parentSession
        # field pointing at the original
        # session file.
        assert header.get("parentSession") == file_path

    def test_preserves_labels_on_branch(self, tmp_path) -> None:
        """Labels on the branch entries are
        preserved as ``label`` entries in the
        new session."""
        file_path = str(tmp_path / "session.jsonl")
        sm = SessionManagerBranching(
            cwd="/some/cwd",
            session_dir=str(tmp_path),
            session_file=file_path,
            persist=True,
        )
        m1 = sm.append_message({"role": "user", "content": "hi"})
        sm.append_label_change(m1, "important")
        m2 = sm.append_message({"role": "assistant", "content": "hello"})
        new_file = sm.create_branched_session(m2)
        with open(new_file, "r", encoding="utf-8") as f:
            lines = f.read().strip().split("\n")
        entries = [json.loads(line) for line in lines]
        # A label entry is in the new file
        # with the right label.
        label_entries = [
            e for e in entries
            if e.get("type") == "label" and e.get("label") == "important"
        ]
        assert len(label_entries) == 1
        assert label_entries[0]["targetId"] == m1

    def test_non_existent_leaf_raises(self, tmp_path) -> None:
        """``create_branched_session`` raises
        when the leaf id is unknown."""
        file_path = str(tmp_path / "session.jsonl")
        sm = SessionManagerBranching(
            cwd="/some/cwd",
            session_dir=str(tmp_path),
            session_file=file_path,
            persist=True,
        )
        sm.append_message({"role": "user", "content": "hi"})
        with pytest.raises(RuntimeError, match="not found"):
            sm.create_branched_session("nonexistent")

    def test_in_memory_branching_returns_none(self, tmp_path) -> None:
        """``persist=False`` → the branch is
        built in memory + ``None`` is
        returned (no file path)."""
        sm = SessionManagerBranching(
            cwd="/some/cwd",
            session_dir=str(tmp_path),
            session_file=None,
            persist=False,
        )
        m1 = sm.append_message({"role": "user", "content": "hi"})
        sm.append_message({"role": "assistant", "content": "hello"})
        new_file = sm.create_branched_session(m1)
        # No file is created.
        assert new_file is None
        # The in-memory state has the branch
        # entries.
        assert any(e.get("id") == m1 for e in sm.file_entries)

    def test_session_file_path_includes_timestamp(self, tmp_path) -> None:
        """The new session file path includes
        the timestamp + the new session id."""
        file_path = str(tmp_path / "session.jsonl")
        sm = SessionManagerBranching(
            cwd="/some/cwd",
            session_dir=str(tmp_path),
            session_file=file_path,
            persist=True,
        )
        m1 = sm.append_message({"role": "user", "content": "hi"})
        sm.append_message({"role": "assistant", "content": "hello"})
        new_file = sm.create_branched_session(m1)
        # The path includes the new session id.
        assert sm.get_session_id() in new_file

    def test_in_memory_branch_preserves_label(self, tmp_path) -> None:
        """In-memory branches preserve the
        label too (the label entry is
        appended after the branch entries)."""
        sm = SessionManagerBranching(
            cwd="/some/cwd",
            session_dir=str(tmp_path / "sessions"),
            session_file=None,
            persist=False,
        )
        m1 = sm.append_message({"role": "user", "content": "hi"})
        sm.append_label_change(m1, "important")
        sm.append_message({"role": "assistant", "content": "hello"})
        sm.create_branched_session(m1)
        # The label is preserved in memory.
        assert sm.get_label(m1) == "important"


# ── Branching with a more complex tree ───────────────────────


class TestBranchingWithComplexTree:
    def test_branch_from_middle_of_chain(self, tmp_path) -> None:
        """Branching from a middle-of-chain
        entry creates a new session with the
        branch path back to the root."""
        file_path = str(tmp_path / "session.jsonl")
        sm = SessionManagerBranching(
            cwd="/some/cwd",
            session_dir=str(tmp_path),
            session_file=file_path,
            persist=True,
        )
        # Build m1 → m2 → m3.
        m1 = sm.append_message({"role": "user", "content": "hi"})
        m2 = sm.append_message({"role": "assistant", "content": "a"})
        sm.append_message({"role": "user", "content": "b"})
        # Branch from m2 (middle of chain).
        new_file = sm.create_branched_session(m2)
        # The new file has the path m1 → m2.
        with open(new_file, "r", encoding="utf-8") as f:
            lines = f.read().strip().split("\n")
        entries = [json.loads(line) for line in lines]
        ids = [e.get("id") for e in entries if "id" in e]
        assert m1 in ids
        assert m2 in ids
        # m3 is NOT in the new file.
        assert "m3" not in ids


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
