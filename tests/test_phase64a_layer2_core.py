"""Phase 6.4a — Layer 2 session core (base class).

Tests for :class:`jarvis.agents.sessions.session_manager_core.SessionManagerCore`.

- Constructor with no file (new session)
- Constructor with existing file
- Constructor with sqlite marker (stub path)
- ``new_session`` resets state
- ``set_loaded_session_file`` recovers from
  a corrupt header
- ``set_loaded_session_file`` migrates
  older versions
- ``build_index`` walks file entries + opaque
  controls
- ``resolve_canonical_parent_id`` walks the
  opaque chain
- ``resolve_branch_target_id`` returns the
  canonical parent or ``None``
- ``create_leaf_control`` + ``remember_leaf_control``
  add an opaque entry
- ``get_persisted_file_entries`` interleaves
  opaque + file entries
- ``replace_persisted_transcript`` writes the
  full file
- ``get_cwd`` / ``get_session_dir`` / ``get_session_id``
  / ``get_session_file`` / ``is_persisted`` /
  ``was_recovered_from_corrupt_header``
"""
from __future__ import annotations

import json
import os
import sys
from typing import Any

import pytest

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_THIS_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from src.agents.sessions import (  # noqa: E402
    CURRENT_SESSION_VERSION,
    SessionFileSnapshot,
    SessionManagerCore,
    create_session_id,
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
    parent_id: Any = None,
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


# ── Constructor: new session ─────────────────────────────────


class TestConstructorNewSession:
    def test_new_session_with_no_file(self, tmp_path) -> None:
        """No file path → :meth:`new_session` runs."""
        agent_dir = str(tmp_path / "agent")
        session_dir = os.path.join(agent_dir, "sessions", "--some-cwd--")
        sm = SessionManagerCore(
            cwd="/some/cwd",
            session_dir=session_dir,
            session_file=None,
            persist=True,
        )
        assert sm.get_session_id() != ""
        assert sm.get_session_file() is not None
        assert sm.get_session_file().endswith(".jsonl")
        # The header is in place.
        header = sm.file_entries[0]
        assert header["type"] == "session"
        assert header["version"] == CURRENT_SESSION_VERSION
        assert header["cwd"] == "/some/cwd"
        # Not yet flushed.
        assert sm.flushed is False

    def test_new_session_with_persist_false(self, tmp_path) -> None:
        """``persist=False`` → no session_file is created."""
        sm = SessionManagerCore(
            cwd="/some/cwd",
            session_dir=str(tmp_path / "sessions"),
            session_file=None,
            persist=False,
        )
        assert sm.get_session_file() is None
        assert sm.is_persisted() is False

    def test_new_session_creates_directory(self, tmp_path) -> None:
        """``persist=True`` creates the session dir."""
        session_dir = str(tmp_path / "deep" / "sessions" / "--x--")
        sm = SessionManagerCore(
            cwd="/x",
            session_dir=session_dir,
            session_file=None,
            persist=True,
        )
        assert os.path.isdir(session_dir)


# ── Constructor: existing file ───────────────────────────────


class TestConstructorExistingFile:
    def test_loads_existing_v3_file(self, tmp_path) -> None:
        """Loads a v3 file with one message."""
        file_path = str(tmp_path / "session.jsonl")
        header = _v3_header()
        msg = _v3_message("m1", parent_id=None, content="hi")
        _write_session_file(file_path, header, msg)
        sm = SessionManagerCore(
            cwd="/some/cwd",
            session_dir=str(tmp_path),
            session_file=file_path,
            persist=True,
        )
        assert sm.get_session_id() == "s1"
        assert sm.flushed is True
        assert sm.was_recovered_from_corrupt_header() is False
        # The index picked up the message.
        assert sm.leaf_id == "m1"
        assert sm.append_parent_id == "m1"
        assert "m1" in sm.by_id

    def test_loads_existing_v1_file_migrates(self, tmp_path) -> None:
        """A v1 file (no ``version`` field) is
        migrated to v3 on load."""
        file_path = str(tmp_path / "v1.jsonl")
        # A v1 file: no ``version`` field, uses
        # ``hookMessage`` (which migrates to
        # ``custom`` in v3).
        header = {
            "type": "session",
            "id": "s1",
            "timestamp": "2026-01-01T00:00:00.000Z",
            "cwd": "/some/cwd",
        }
        msg = {
            "type": "message",
            "id": "m1",
            "parentId": None,
            "timestamp": "2026-01-01T00:00:00.000Z",
            "message": {"role": "user", "content": "hi"},
        }
        _write_session_file(file_path, header, msg)
        sm = SessionManagerCore(
            cwd="/some/cwd",
            session_dir=str(tmp_path),
            session_file=file_path,
            persist=True,
        )
        # The migrated file is on disk.
        with open(file_path, "r", encoding="utf-8") as f:
            lines = f.read().strip().split("\n")
        # The header now has version=3.
        header_line = json.loads(lines[0])
        assert header_line["version"] == CURRENT_SESSION_VERSION


# ── setLoadedSessionFile: corrupt recovery ───────────────────


class TestCorruptRecovery:
    def test_recovers_from_corrupt_header(self, tmp_path) -> None:
        """A file with only non-recognised
        entries (no session header + no indexed
        entry types) triggers the recovery path.
        The recovery creates a fresh header +
        preserves the opaque rows + writes a
        backup."""
        file_path = str(tmp_path / "corrupt.jsonl")
        # Use a non-recognised type so the
        # partition function drops them into
        # ``opaqueEntries`` (not ``fileEntries``).
        # ``fileEntries.length === 0`` triggers
        # the recovery path.
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(
                json.dumps({"foo": "bar", "value": 1}) + "\n"
            )
            f.write(
                json.dumps({"baz": "qux", "value": 2}) + "\n"
            )
        sm = SessionManagerCore(
            cwd="/some/cwd",
            session_dir=str(tmp_path),
            session_file=file_path,
            persist=True,
        )
        # The recovery path was taken.
        assert sm.was_recovered_from_corrupt_header() is True
        # A fresh session header was created.
        header = sm.file_entries[0]
        assert header["type"] == "session"
        assert header["version"] == CURRENT_SESSION_VERSION
        # The opaque rows are preserved.
        assert len(sm.opaque_file_entries) >= 2
        # A backup was created.
        backup_files = [
            p for p in os.listdir(tmp_path)
            if p.startswith("corrupt.jsonl.corrupt-")
        ]
        assert len(backup_files) == 1

    def test_empty_file_creates_new_session(self, tmp_path) -> None:
        """An empty file → a fresh session is
        created (no recovery)."""
        file_path = str(tmp_path / "empty.jsonl")
        open(file_path, "w").close()
        sm = SessionManagerCore(
            cwd="/some/cwd",
            session_dir=str(tmp_path),
            session_file=file_path,
            persist=True,
        )
        # No corrupt recovery (nothing to recover).
        assert sm.was_recovered_from_corrupt_header() is False
        # The session was re-initialised; the
        # session_id is a fresh one.
        assert sm.get_session_id() != "s1"


# ── newSession: reset state ──────────────────────────────────


class TestNewSessionReset:
    def test_new_session_resets_state(self, tmp_path) -> None:
        """``new_session`` clears all indexes + the
        file-entries + opaque state."""
        file_path = str(tmp_path / "session.jsonl")
        _write_session_file(file_path, _v3_header(), _v3_message("m1"))
        sm = SessionManagerCore(
            cwd="/some/cwd",
            session_dir=str(tmp_path),
            session_file=file_path,
            persist=True,
        )
        # State was loaded.
        assert "m1" in sm.by_id
        old_id = sm.get_session_id()
        # Start a new session.
        new_path = sm.new_session()
        assert new_path is not None
        assert sm.get_session_id() != old_id
        assert sm.leaf_id is None
        assert sm.append_parent_id is None
        assert sm.by_id == {}
        assert sm.opaque_parents_by_id == {}
        assert sm.file_entries[0]["type"] == "session"
        assert sm.flushed is False


# ── buildIndex: leaf + opaque walk ───────────────────────────


class TestBuildIndex:
    def test_walks_file_entries(self, tmp_path) -> None:
        """``build_index`` walks the file entries
        and updates the leaf + appendParent."""
        file_path = str(tmp_path / "walk.jsonl")
        _write_session_file(
            file_path,
            _v3_header(),
            _v3_message("m1", role="user", parent_id=None),
            _v3_message("m2", role="assistant", parent_id="m1"),
        )
        sm = SessionManagerCore(
            cwd="/some/cwd",
            session_dir=str(tmp_path),
            session_file=file_path,
            persist=True,
        )
        assert sm.leaf_id == "m2"
        assert sm.append_parent_id == "m2"
        assert "m1" in sm.by_id
        assert "m2" in sm.by_id

    def test_label_entry_updates_labels(self, tmp_path) -> None:
        """A ``label`` entry updates ``labels_byId``."""
        file_path = str(tmp_path / "labels.jsonl")
        _write_session_file(
            file_path,
            _v3_header(),
            _v3_message("m1", parent_id=None),
            {
                "type": "label",
                "id": "l1",
                "parentId": "m1",
                "timestamp": "2026-01-01T00:00:00.000Z",
                "targetId": "m1",
                "label": "first",
            },
        )
        sm = SessionManagerCore(
            cwd="/some/cwd",
            session_dir=str(tmp_path),
            session_file=file_path,
            persist=True,
        )
        assert sm.labels_by_id.get("m1") == "first"
        assert sm.label_timestamps_by_id.get("m1") is not None


# ── resolveCanonicalParentId / resolveBranchTargetId ─────────


class TestResolveHelpers:
    def test_resolve_canonical_parent_id_walks_opaque(self, tmp_path) -> None:
        """``resolveCanonicalParentId`` walks the
        opaque-parent chain until a known id is
        found (or the cycle is detected)."""
        file_path = str(tmp_path / "chain.jsonl")
        _write_session_file(file_path, _v3_header(), _v3_message("m1"))
        sm = SessionManagerCore(
            cwd="/some/cwd",
            session_dir=str(tmp_path),
            session_file=file_path,
            persist=True,
        )
        # ``m1`` is a known id → returns m1.
        assert sm.resolve_canonical_parent_id("m1") == "m1"
        # ``None`` → None.
        assert sm.resolve_canonical_parent_id(None) is None
        # Unknown id with no opaque parent → None.
        assert sm.resolve_canonical_parent_id("unknown") is None

    def test_resolve_branch_target_id(self, tmp_path) -> None:
        file_path = str(tmp_path / "branch.jsonl")
        _write_session_file(
            file_path,
            _v3_header(),
            _v3_message("m1", parent_id=None),
            _v3_message("m2", parent_id="m1"),
        )
        sm = SessionManagerCore(
            cwd="/some/cwd",
            session_dir=str(tmp_path),
            session_file=file_path,
            persist=True,
        )
        # Known id → returned.
        assert sm.resolve_branch_target_id("m1") == "m1"
        # Unknown id with no opaque parent → None.
        assert sm.resolve_branch_target_id("unknown") is None


# ── createLeafControl + rememberLeafControl ───────────────────


class TestLeafControl:
    def test_create_leaf_control(self, tmp_path) -> None:
        file_path = str(tmp_path / "leaf.jsonl")
        _write_session_file(file_path, _v3_header(), _v3_message("m1"))
        sm = SessionManagerCore(
            cwd="/some/cwd",
            session_dir=str(tmp_path),
            session_file=file_path,
            persist=True,
        )
        leaf = sm.create_leaf_control(parent_id="m1")
        assert leaf["type"] == "leaf"
        assert leaf["parentId"] == "m1"
        assert leaf["targetId"] == "m1"  # current leaf
        assert "id" in leaf
        assert "timestamp" in leaf

    def test_remember_leaf_control(self, tmp_path) -> None:
        file_path = str(tmp_path / "remember.jsonl")
        _write_session_file(file_path, _v3_header(), _v3_message("m1"))
        sm = SessionManagerCore(
            cwd="/some/cwd",
            session_dir=str(tmp_path),
            session_file=file_path,
            persist=True,
        )
        leaf = sm.create_leaf_control(parent_id="m1")
        sm.remember_leaf_control(leaf)
        assert len(sm.opaque_file_entries) == 1
        assert leaf["id"] in sm.opaque_parents_by_id
        assert sm.opaque_parents_by_id[leaf["id"]] == "m1"


# ── getPersistedFileEntries ──────────────────────────────────


class TestGetPersistedFileEntries:
    def test_interleaves_opaque_and_file(self, tmp_path) -> None:
        """Opaque entries are interleaved at their
        stored index."""
        file_path = str(tmp_path / "interleave.jsonl")
        _write_session_file(
            file_path,
            _v3_header(),
            _v3_message("m1", parent_id=None),
            _v3_message("m2", parent_id="m1"),
        )
        sm = SessionManagerCore(
            cwd="/some/cwd",
            session_dir=str(tmp_path),
            session_file=file_path,
            persist=True,
        )
        # Add a leaf control at the tail.
        leaf = sm.create_leaf_control(parent_id="m2")
        sm.remember_leaf_control(leaf)
        entries = sm.get_persisted_file_entries()
        # The first entry is the session header,
        # then m1, m2, then the leaf control.
        assert entries[0]["type"] == "session"
        assert entries[1]["id"] == "m1"
        assert entries[2]["id"] == "m2"
        # The leaf control is at the tail (the
        # index was len(file_entries) = 3, but
        # the persisted-entries may push it to
        # the end via the auto-add fallback).
        last = entries[-1]
        assert last["type"] == "leaf" or last["id"] == leaf["id"]


# ── replacePersistedTranscript / writeFullFile ───────────────


class TestReplacePersistedTranscript:
    def test_writes_full_file(self, tmp_path) -> None:
        file_path = str(tmp_path / "session.jsonl")
        sm = SessionManagerCore(
            cwd="/some/cwd",
            session_dir=str(tmp_path),
            session_file=file_path,
            persist=True,
        )
        sm.write_full_file()
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        # The file contains the session header.
        assert "session" in content

    def test_replace_persisted_transcript_noop_when_not_persisted(
        self, tmp_path
    ) -> None:
        """``persist=False`` → no file is written."""
        sm = SessionManagerCore(
            cwd="/some/cwd",
            session_dir=str(tmp_path),
            session_file=None,
            persist=False,
        )
        # No error, no file.
        sm.replace_persisted_transcript()
        # The session_file is still None.
        assert sm.get_session_file() is None


# ── Getters ──────────────────────────────────────────────────


class TestGetters:
    def test_getters(self, tmp_path) -> None:
        file_path = str(tmp_path / "getters.jsonl")
        _write_session_file(file_path, _v3_header(sid="abc123"))
        sm = SessionManagerCore(
            cwd="/some/cwd",
            session_dir=str(tmp_path),
            session_file=file_path,
            persist=True,
        )
        assert sm.get_cwd() == "/some/cwd"
        assert sm.get_session_dir() == str(tmp_path)
        assert sm.get_session_id() == "abc123"
        assert sm.get_session_file() == file_path
        assert sm.is_persisted() is True
        assert sm.was_recovered_from_corrupt_header() is False


# ── clearPreservedOpaqueFileEntries ──────────────────────────


class TestClearOpaque:
    def test_clears_opaque_state(self, tmp_path) -> None:
        file_path = str(tmp_path / "clear.jsonl")
        _write_session_file(file_path, _v3_header(), _v3_message("m1"))
        sm = SessionManagerCore(
            cwd="/some/cwd",
            session_dir=str(tmp_path),
            session_file=file_path,
            persist=True,
        )
        leaf = sm.create_leaf_control(parent_id="m1")
        sm.remember_leaf_control(leaf)
        assert len(sm.opaque_file_entries) == 1
        sm.clear_preserved_opaque_file_entries()
        assert sm.opaque_file_entries == []
        assert sm.opaque_parents_by_id == {}
        assert sm.invalid_leaf_control_ids == set()
        assert sm.append_parent_id is None
        assert sm.prompt_released_side_branch_parent_id is None


# ── clampOpaqueFileEntryIndexes ─────────────────────────────


class TestClampOpaqueIndexes:
    def test_clamps_indexes_within_range(self, tmp_path) -> None:
        file_path = str(tmp_path / "clamp.jsonl")
        _write_session_file(file_path, _v3_header(), _v3_message("m1"))
        sm = SessionManagerCore(
            cwd="/some/cwd",
            session_dir=str(tmp_path),
            session_file=file_path,
            persist=True,
        )
        # Add an opaque entry with a too-large
        # index — the clamp should bring it
        # back into range.
        sm.opaque_file_entries.append(
            {"index": 999, "record": {"type": "leaf", "id": "x", "parentId": None, "timestamp": "t", "targetId": None}}
        )
        sm.clamp_opaque_file_entry_indexes()
        for opaque_entry in sm.opaque_file_entries:
            assert 0 <= opaque_entry["index"] <= len(sm.file_entries)


# ── getSerializedFileLinesForRewrite ─────────────────────────


class TestGetSerializedFileLinesForRewrite:
    def test_returns_jsonl_lines(self, tmp_path) -> None:
        file_path = str(tmp_path / "rewrite.jsonl")
        _write_session_file(file_path, _v3_header(), _v3_message("m1"))
        sm = SessionManagerCore(
            cwd="/some/cwd",
            session_dir=str(tmp_path),
            session_file=file_path,
            persist=True,
        )
        lines = sm.get_serialized_file_lines_for_rewrite()
        assert len(lines) >= 1
        for line in lines:
            # Each line is a JSON object.
            parsed = json.loads(line)
            assert isinstance(parsed, dict)


# ── normalizeEntryParent ────────────────────────────────────


class TestNormalizeEntryParent:
    def test_returns_entry_with_resolved_parent(self, tmp_path) -> None:
        file_path = str(tmp_path / "norm.jsonl")
        _write_session_file(file_path, _v3_header(), _v3_message("m1"))
        sm = SessionManagerCore(
            cwd="/some/cwd",
            session_dir=str(tmp_path),
            session_file=file_path,
            persist=True,
        )
        # The entry's parent is already None (the
        # m1 message has parentId=None). The
        # normalized form is the entry itself.
        normalized = sm.normalize_entry_parent(sm.by_id["m1"])
        assert normalized["id"] == "m1"


# ── inMemory: session without persistence ────────────────────


class TestInMemorySession:
    def test_in_memory_session(self, tmp_path) -> None:
        """A session with ``persist=False`` is a
        pure in-memory session — no file is
        created, no file is read."""
        sm = SessionManagerCore(
            cwd="/x",
            session_dir=str(tmp_path / "sessions"),
            session_file=None,
            persist=False,
        )
        assert sm.get_session_file() is None
        assert sm.is_persisted() is False
        # The header is in memory.
        header = sm.file_entries[0]
        assert header["type"] == "session"
        assert header["cwd"] == "/x"


# ── sqlite marker constructor (stub path) ──────────────────


class TestSqliteMarkerStub:
    def test_sqlite_marker_constructor_runs(self, tmp_path) -> None:
        """The sqlite marker constructor path
        loads a stub session from a marker.

        Phase 6.4a ships the marker-loading
        code path; the underlying
        ``load_events`` callback is a stub that
        returns ``[]`` (Phase 6.5 wires the
        full transcript-DB read). The
        constructor still produces a valid
        session manager."""
        sm = SessionManagerCore(
            cwd="/x",
            session_dir=str(tmp_path / "sessions"),
            session_file="sqlite:agent1:s1:/store",
            persist=True,
            sqlite_persistence={
                "agent_id": "agent1",
                "session_id": "s1",
                "store_path": "/store",
                "session_key": "s1",
            },
        )
        # The constructor took the sqlite path
        # (no set_loaded_session_file was called).
        # The session is a new-session.
        assert sm.get_session_id() == "s1"
        assert sm.sqlite_persistence is not None
        assert sm.sqlite_persistence["agent_id"] == "agent1"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
