"""Phase 6.5 — Layer 2 session manager facade.

Tests for
:class:`jarvis.agents.sessions.session_manager.SessionManager`
static factories + class behaviour.

- ``SessionManager.create(cwd, session_dir?)`` —
  fresh file-backed session.
- ``SessionManager.open(path, session_dir?, cwd_override?)`` —
  load an existing file (or sqlite marker
  via the file-fallback path).
- ``SessionManager.continue_recent(cwd, session_dir?)`` —
  resume the most-recent session for
  ``cwd``.
- ``SessionManager.in_memory(cwd?)`` —
  pure in-memory session.
- ``SessionManager.fork_from(source_path, target_cwd, session_dir?)`` —
  fork a session file into a new one.
- ``SessionManager.list(cwd, session_dir?)`` /
  ``list_all()`` — async static listers.
- The facade exposes every inherited method
  (the public surface of the
  :class:`SessionManagerBranching` parent).
- :class:`ReadonlySessionManager` exposes the
  read-only view.
"""
from __future__ import annotations

import asyncio
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
    ReadonlySessionManager,
    SessionManager,
    SessionManagerBranching,
    SessionManagerCore,
    SessionManagerEntries,
    SessionManagerPersistence,
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
) -> dict:
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


# ── SessionManager.create ────────────────────────────────────


class TestSessionManagerCreate:
    def test_creates_new_session(self, tmp_path) -> None:
        """``SessionManager.create`` produces a
        fresh file-backed session."""
        sm = SessionManager.create(
            cwd="/some/cwd",
            session_dir=str(tmp_path / "sessions" / "--some-cwd--"),
        )
        assert sm.is_persisted() is True
        assert sm.get_session_file() is not None
        # The session id is a UUID.
        assert sm.get_session_id() != ""


# ── SessionManager.open ───────────────────────────────────────


class TestSessionManagerOpen:
    def test_opens_existing_file(self, tmp_path) -> None:
        """``SessionManager.open`` loads an
        existing session file."""
        file_path = str(tmp_path / "session.jsonl")
        _write_session_file(
            file_path,
            _v3_header(sid="abc123"),
            _v3_message("m1", role="user", parent_id=None),
        )
        sm = SessionManager.open(
            path=file_path,
        )
        assert sm.get_session_id() == "abc123"
        assert sm.leaf_id == "m1"
        assert "m1" in sm.by_id

    def test_opens_with_cwd_override(self, tmp_path) -> None:
        """``cwd_override`` rewrites the cwd."""
        file_path = str(tmp_path / "session.jsonl")
        _write_session_file(file_path, _v3_header(cwd="/old/cwd", sid="abc"))
        sm = SessionManager.open(
            path=file_path,
            cwd_override="/new/cwd",
        )
        assert sm.get_cwd() == "/new/cwd"


# ── SessionManager.continueRecent ─────────────────────────────


class TestSessionManagerContinueRecent:
    def test_continues_recent_session(self, tmp_path) -> None:
        """``continue_recent`` opens the
        most-recent session for ``cwd``."""
        session_dir = str(tmp_path / "sessions" / "--some-cwd--")
        os.makedirs(session_dir, exist_ok=True)
        # Create a session file.
        old_path = os.path.join(session_dir, "old.jsonl")
        new_path = os.path.join(session_dir, "new.jsonl")
        _write_session_file(old_path, _v3_header(sid="old"))
        import time
        time.sleep(0.01)
        _write_session_file(new_path, _v3_header(sid="new"))
        sm = SessionManager.continue_recent(
            cwd="/some/cwd",
            session_dir=session_dir,
        )
        # The most-recent session is loaded.
        assert sm.get_session_id() == "new"
        assert sm.get_session_file() == new_path

    def test_continues_when_no_recent(self, tmp_path) -> None:
        """No recent session → a fresh session is
        created."""
        session_dir = str(tmp_path / "sessions" / "--some-cwd--")
        sm = SessionManager.continue_recent(
            cwd="/some/cwd",
            session_dir=session_dir,
        )
        # A new session is created (no file
        # loaded).
        assert sm.get_session_file() is not None


# ── SessionManager.inMemory ───────────────────────────────────


class TestSessionManagerInMemory:
    def test_in_memory_session(self) -> None:
        """``in_memory`` creates a non-persisted
        session."""
        sm = SessionManager.in_memory(cwd="/some/cwd")
        assert sm.is_persisted() is False
        assert sm.get_session_file() is None
        # The header is in memory.
        header = next(
            e for e in sm.file_entries if e.get("type") == "session"
        )
        assert header["cwd"] == "/some/cwd"


# ── SessionManager.forkFrom ────────────────────────────────────


class TestSessionManagerForkFrom:
    def test_fork_creates_new_file(self, tmp_path) -> None:
        """``fork_from`` creates a new session
        file with the source entries."""
        source_path = str(tmp_path / "source.jsonl")
        _write_session_file(
            source_path,
            _v3_header(sid="src"),
            _v3_message("m1", role="user", parent_id=None),
        )
        target_dir = str(tmp_path / "sessions" / "--other-cwd--")
        sm = SessionManager.fork_from(
            source_path=source_path,
            target_cwd="/other/cwd",
            session_dir=target_dir,
        )
        # The new file exists.
        assert sm.get_session_file() is not None
        assert os.path.exists(sm.get_session_file())
        # The new session id is fresh.
        assert sm.get_session_id() != "src"
        # The cwd is the new one.
        assert sm.get_cwd() == "/other/cwd"
        # The source entries are copied.
        with open(sm.get_session_file(), "r", encoding="utf-8") as f:
            content = f.read()
        assert "session" in content
        assert "m1" in content
        # The new header has a parentSession
        # field.
        with open(sm.get_session_file(), "r", encoding="utf-8") as f:
            first_line = json.loads(f.readline())
        assert first_line.get("parentSession") == source_path

    def test_fork_empty_source_raises(self, tmp_path) -> None:
        """``fork_from`` on an empty file raises."""
        source_path = str(tmp_path / "empty.jsonl")
        open(source_path, "w").close()
        with pytest.raises(RuntimeError, match="empty or invalid"):
            SessionManager.fork_from(
                source_path=source_path,
                target_cwd="/x",
            )

    def test_fork_no_header_raises(self, tmp_path) -> None:
        """``fork_from`` on a file with no header
        raises (the OpenClaw source's
        ``loadEntriesFromFile`` filters out
        files with no readable header, so the
        first check fires)."""
        source_path = str(tmp_path / "no_header.jsonl")
        with open(source_path, "w", encoding="utf-8") as f:
            f.write(json.dumps(_v3_message("m1", parent_id=None)) + "\n")
        with pytest.raises(RuntimeError, match="empty or invalid"):
            SessionManager.fork_from(
                source_path=source_path,
                target_cwd="/x",
            )


# ── SessionManager.list / listAll ────────────────────────────


class TestSessionManagerList:
    def test_list(self, tmp_path) -> None:
        """``SessionManager.list`` returns the
        sessions for ``cwd``."""
        session_dir = str(tmp_path / "sessions" / "--some-cwd--")
        os.makedirs(session_dir, exist_ok=True)
        # Two sessions for the cwd, one for
        # another.
        _write_session_file(
            os.path.join(session_dir, "a.jsonl"),
            _v3_header(cwd="/some/cwd", sid="a"),
        )
        _write_session_file(
            os.path.join(session_dir, "b.jsonl"),
            _v3_header(cwd="/some/cwd", sid="b"),
        )
        _write_session_file(
            os.path.join(session_dir, "c.jsonl"),
            _v3_header(cwd="/other", sid="c"),
        )
        sessions = asyncio.run(
            SessionManager.list(
                cwd="/some/cwd",
                session_dir=session_dir,
            )
        )
        ids = {s.id for s in sessions}
        assert ids == {"a", "b"}

    def test_list_all(self, tmp_path, monkeypatch) -> None:
        """``SessionManager.list_all`` returns
        every session across all sub-dirs.

        The default sessions dir is
        ``~/.jarvis/agents/default/sessions``;
        we monkey-patch the resolver to point at
        the test's ``tmp_path`` so the test
        doesn't touch the operator's state."""
        sessions_dir = str(tmp_path / "sessions")
        # Two sub-dirs with one file each.
        d1 = os.path.join(sessions_dir, "agent1")
        d2 = os.path.join(sessions_dir, "agent2")
        os.makedirs(d1)
        os.makedirs(d2)
        _write_session_file(
            os.path.join(d1, "a.jsonl"),
            _v3_header(cwd="/cwd1", sid="a"),
        )
        _write_session_file(
            os.path.join(d2, "b.jsonl"),
            _v3_header(cwd="/cwd2", sid="b"),
        )
        # Monkey-patch the sessions dir resolver.
        import src.agents.sessions.session_manager_list as sml
        monkeypatch.setattr(
            sml, "_sessions_dir_default", lambda: sessions_dir
        )
        sessions = asyncio.run(SessionManager.list_all())
        ids = {s.id for s in sessions}
        assert ids == {"a", "b"}


# ── Inherited public surface ──────────────────────────────────


class TestInheritedSurface:
    def test_extends_session_manager_branching(self) -> None:
        """``SessionManager`` is a subclass of
        ``SessionManagerBranching``."""
        assert issubclass(SessionManager, SessionManagerBranching)
        assert issubclass(SessionManager, SessionManagerEntries)
        assert issubclass(SessionManager, SessionManagerPersistence)
        assert issubclass(SessionManager, SessionManagerCore)

    def test_inherited_methods_work(self, tmp_path) -> None:
        """The inherited append + branch methods
        are usable on the facade."""
        sm = SessionManager.create(
            cwd="/some/cwd",
            session_dir=str(tmp_path / "sessions" / "--some-cwd--"),
        )
        # Append a message.
        sm.append_message({"role": "user", "content": "hi"})
        sm.append_message({"role": "assistant", "content": "hello"})
        # Branch.
        m1_id = next(
            e["id"]
            for e in sm.file_entries
            if e.get("type") == "message"
            and e.get("message", {}).get("role") == "user"
        )
        # The facade exposes ``branch``.
        sm.branch(m1_id)
        assert sm.get_leaf_id() == m1_id


# ── ReadonlySessionManager ────────────────────────────────────


class TestReadonlySessionManager:
    def test_readonly_view(self, tmp_path) -> None:
        """``ReadonlySessionManager`` exposes the
        read-only methods of the underlying
        :class:`SessionManager`."""
        sm = SessionManager.create(
            cwd="/some/cwd",
            session_dir=str(tmp_path / "sessions" / "--some-cwd--"),
        )
        sm.append_message({"role": "user", "content": "hi"})
        sm.append_message({"role": "assistant", "content": "hello"})
        ro = ReadonlySessionManager(sm)
        # The read-only view exposes the
        # read-only methods.
        assert ro.get_cwd() == "/some/cwd"
        assert ro.get_leaf_id() is not None
        assert ro.get_session_name() is None
        # The branch is the user + assistant
        # messages.
        branch = ro.get_branch()
        assert len(branch) == 2
        # The tree is built.
        tree = ro.get_tree()
        assert len(tree) >= 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
