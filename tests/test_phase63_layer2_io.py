"""Phase 6.3 — Layer 2 session IO + discovery.

These tests prove the Phase-6.3 session-IO +
discovery modules in ``src/agents/sessions/``
match the OpenClaw source contract for:

- ``session_manager_file``:
  - ``get_default_session_dir(cwd, agent_dir?)`` —
    ``<agent_dir>/sessions/--<sanitized_cwd>--``
  - ``load_entries_from_file(path)`` — load the
    entries; ``[]`` when missing or header-less
  - ``load_entries_from_file_with_snapshot(path)``
    — snapshot-checked load
  - ``revalidate_loaded_session_file(path, loaded)``
    — re-check via snapshot
  - ``session_file_needs_append_separator(path, snapshot)``
    — last byte != newline?
  - ``load_sqlite_marked_session_file(path, load_events)``
    — SQLite-marker session loader
  - ``recover_corrupt_session_entries(path, cwd)`` —
    backup + recover
  - ``read_session_file_snapshot(path)`` /
    ``read_session_file_snapshot_if_exists(path)``
  - ``json_serialization_can_run_user_code(value)``
  - ``message_serializes_owned_values(message)``
  - ``remember_written_session_entries(path, expected_content?)``
  - ``remember_appended_session_entry(params)``
  - ``can_publish_owned_session_append(session_file, snapshot)``
- ``session_manager_list``:
  - ``find_most_recent_session(session_dir, cwd?)``
  - ``list_sessions(cwd, session_dir, on_progress?)``
  - ``list_all_sessions(on_progress?)``
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time

import pytest

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_THIS_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from src.agents.sessions import (  # noqa: E402
    CURRENT_SESSION_VERSION,
    MAX_CACHED_SESSION_BYTES,
    MAX_CACHED_SESSION_FILES,
    LoadedSessionFile,
    SessionFileSnapshot,
    can_publish_owned_session_append,
    find_most_recent_session,
    get_default_session_dir,
    json_serialization_can_run_user_code,
    list_all_sessions,
    list_sessions,
    load_entries_from_file,
    load_entries_from_file_with_snapshot,
    load_sqlite_marked_session_file,
    message_serializes_owned_values,
    publish_remembered_session_file_snapshot,
    read_session_file_snapshot,
    read_session_file_snapshot_if_exists,
    recover_corrupt_session_entries,
    remember_appended_session_entry,
    remember_written_session_entries,
    revalidate_loaded_session_file,
    session_file_needs_append_separator,
)


# ── session_manager_file — constants
# ─────────────────────────────────────


class TestFileConstants:
    def test_max_cached_session_files(self) -> None:
        """Mirrors ``MAX_CACHED_SESSION_FILES``
        (``session-manager-file.ts:37``)."""
        assert MAX_CACHED_SESSION_FILES == 8

    def test_max_cached_session_bytes(self) -> None:
        """Mirrors ``MAX_CACHED_SESSION_BYTES``
        (``session-manager-file.ts:38``). 32 MB."""
        assert MAX_CACHED_SESSION_BYTES == 32 * 1024 * 1024


# ── session_manager_file — getDefaultSessionDir
# ──────────────────────────


class TestGetDefaultSessionDir:
    def test_creates_directory(self, tmp_path) -> None:
        """Mirrors ``getDefaultSessionDir``
        (``session-manager-file.ts:60-67``)."""
        agent_dir = str(tmp_path / "agent")
        session_dir = get_default_session_dir(
            cwd="/some/cwd", agent_dir=agent_dir
        )
        # Directory was created.
        assert os.path.isdir(session_dir)
        # The sanitization replaces ``/`` with ``-``;
        # the leading ``/`` is also replaced, giving
        # ``--some-cwd--``. The path is normalised
        # to POSIX separators (the OpenClaw
        # ``path.join`` would emit backslashes on
        # Windows; the Python port emits ``/`` so
        # the on-disk identity + test surface stay
        # stable on every host).
        assert session_dir.replace("\\", "/").endswith(
            "sessions/--some-cwd--"
        )

    def test_sanitizes_special_chars(self, tmp_path) -> None:
        """The OpenClaw source's sanitization
        replaces leading ``/``/``\\`` (only one
        leading char) and any of ``/``, ``\\``,
        ``:`` with ``-``.
        ``session-manager-file.ts:61``."""
        agent_dir = str(tmp_path / "agent")
        # Windows-style path with colons. The
        # sanitizer replaces ``:`` with ``-`` and
        # both ``\\`` chars with ``-``.
        session_dir = get_default_session_dir(
            cwd=r"C:\Users\me", agent_dir=agent_dir
        )
        # The OpenClaw regex
        # ``cwd.replace(/^[/\\]/, "").replace(/[/\\:]/g, "-")``
        # for ``C:\Users\me`` (no leading ``/`` or
        # ``\\``) keeps the ``C`` and replaces
        # the ``:`` and both ``\`` with ``-``:
        # ``C`` + ``-`` + ``-`` + ``Users`` + ``-``
        # + ``me`` → ``C--Users-me`` (the
        # leading-char regex is a no-op here).
        assert "C--Users-me" in session_dir
        # No literal colons / backslashes survive.
        assert ":" not in os.path.basename(session_dir)
        assert "\\" not in os.path.basename(session_dir).replace(
            "--", ""
        )

    def test_preserves_existing_directory(self, tmp_path) -> None:
        agent_dir = str(tmp_path / "agent")
        cwd = "/some/cwd"
        session_dir = get_default_session_dir(
            cwd=cwd, agent_dir=agent_dir
        )
        # Calling again should not error.
        session_dir_2 = get_default_session_dir(
            cwd=cwd, agent_dir=agent_dir
        )
        assert session_dir == session_dir_2


# ── session_manager_file — snapshot helpers
# ──────────────────────────────────


def _write_session_file(file_path: str, header: dict, *entries: dict) -> None:
    """Helper: write a v3 session file with the
    given header + entries."""
    lines = [json.dumps(header)] + [json.dumps(e) for e in entries]
    with open(file_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def _v3_header(cwd: str = "/some/cwd", sid: str = "s1") -> dict:
    return {
        "type": "session",
        "version": CURRENT_SESSION_VERSION,
        "id": sid,
        "timestamp": "2026-01-01T00:00:00.000Z",
        "cwd": cwd,
    }


class TestSnapshotHelpers:
    def test_read_snapshot_returns_dev_ino_size_mtime_ctime(
        self, tmp_path
    ) -> None:
        file_path = str(tmp_path / "snap.jsonl")
        _write_session_file(file_path, _v3_header())
        snap = read_session_file_snapshot(file_path)
        assert snap.dev > 0
        assert snap.ino > 0
        # The empty entries → 1-line file.
        assert snap.size > 0
        assert snap.mtime_ns > 0
        assert snap.ctime_ns > 0

    def test_read_snapshot_if_exists_returns_none_for_missing(
        self, tmp_path
    ) -> None:
        assert (
            read_session_file_snapshot_if_exists(
                str(tmp_path / "missing.jsonl")
            )
            is None
        )

    def test_read_snapshot_if_exists_returns_snapshot(
        self, tmp_path
    ) -> None:
        file_path = str(tmp_path / "snap.jsonl")
        _write_session_file(file_path, _v3_header())
        snap = read_session_file_snapshot_if_exists(file_path)
        assert snap is not None


# ── session_manager_file — loadEntriesFromFile
# ───────────────────────────────────


class TestLoadEntriesFromFile:
    def test_loads_v3_file(self, tmp_path) -> None:
        """Mirrors ``loadEntriesFromFile``
        (``session-manager-file.ts:69-75``)."""
        file_path = str(tmp_path / "ok.jsonl")
        _write_session_file(
            file_path,
            _v3_header(),
            {
                "type": "message",
                "id": "m1",
                "parentId": None,
                "timestamp": "2026-01-01T00:00:00.000Z",
                "message": {"role": "user", "content": "hi"},
            },
        )
        entries = load_entries_from_file(file_path)
        assert len(entries) == 2
        assert entries[0]["type"] == "session"
        assert entries[1]["type"] == "message"

    def test_missing_file_returns_empty(self, tmp_path) -> None:
        assert load_entries_from_file(str(tmp_path / "missing.jsonl")) == []

    def test_file_without_header_returns_empty(self, tmp_path) -> None:
        """Mirrors the ``hasReadableSessionHeader``
        guard (``session-manager-file.ts:74``)."""
        file_path = str(tmp_path / "no_header.jsonl")
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(json.dumps({"type": "message", "id": "m1"}) + "\n")
        assert load_entries_from_file(file_path) == []


# ── session_manager_file — snapshot-load
# ───────────────────────────────


class TestLoadEntriesFromFileWithSnapshot:
    def test_returns_entries_and_snapshot(self, tmp_path) -> None:
        file_path = str(tmp_path / "load.jsonl")
        _write_session_file(file_path, _v3_header())
        loaded = load_entries_from_file_with_snapshot(file_path)
        assert isinstance(loaded, LoadedSessionFile)
        assert loaded.snapshot is not None
        assert len(loaded.entries) == 1
        assert loaded.entries[0]["type"] == "session"

    def test_revalidate_returns_same_when_snapshot_matches(
        self, tmp_path
    ) -> None:
        file_path = str(tmp_path / "revalidate.jsonl")
        _write_session_file(file_path, _v3_header())
        loaded = load_entries_from_file_with_snapshot(file_path)
        # No changes on disk → revalidation returns
        # the same instance.
        revalidated = revalidate_loaded_session_file(
            file_path, loaded
        )
        assert revalidated is loaded


# ── session_manager_file — append separator
# ───────────────────────────────


class TestAppendSeparator:
    def test_empty_snapshot_no_separator(self, tmp_path) -> None:
        """``snapshot.size == 0`` → no separator
        (``session-manager-file.ts:442-444``)."""
        file_path = str(tmp_path / "empty.jsonl")
        # Build a zero-size snapshot.
        snap = SessionFileSnapshot(
            dev=0, ino=0, size=0, mtime_ns=0, ctime_ns=0
        )
        assert (
            session_file_needs_append_separator(file_path, snap)
            is False
        )

    def test_none_snapshot_no_separator(self, tmp_path) -> None:
        assert (
            session_file_needs_append_separator(
                str(tmp_path / "x.jsonl"), None
            )
            is False
        )

    def test_file_ending_with_newline_no_separator(
        self, tmp_path
    ) -> None:
        file_path = str(tmp_path / "ends_with_nl.jsonl")
        _write_session_file(file_path, _v3_header())
        snap = read_session_file_snapshot(file_path)
        # The file ends with ``\n`` (the helper
        # always appends one).
        assert (
            session_file_needs_append_separator(file_path, snap)
            is False
        )

    def test_file_without_trailing_newline_needs_separator(
        self, tmp_path
    ) -> None:
        file_path = str(tmp_path / "no_nl.jsonl")
        # Write without the trailing newline.
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(json.dumps(_v3_header()))
        snap = read_session_file_snapshot(file_path)
        assert (
            session_file_needs_append_separator(file_path, snap)
            is True
        )


# ── session_manager_file — SQLite marker
# ──────────────────────────────


class TestSqliteMarkedSessionFile:
    def test_loads_sqlite_marker(self) -> None:
        """Mirrors ``loadSqliteMarkedSessionFile``
        (``session-manager-file.ts:478-501``)."""
        def load_events(marker):
            return [
                {
                    "type": "session",
                    "version": CURRENT_SESSION_VERSION,
                    "id": "s1",
                    "timestamp": "2026-01-01T00:00:00.000Z",
                    "cwd": "/from/header",
                }
            ]
        result = load_sqlite_marked_session_file(
            "sqlite:agent1:s1:/path/to/store:scope-a",
            load_events=load_events,
        )
        assert result is not None
        assert result["cwd"] == "/from/header"
        assert result["sessionKey"] == "s1"
        assert result["sqliteMarker"]["agent_id"] == "agent1"

    def test_loads_without_cwd_override(self) -> None:
        def load_events(marker):
            return [
                {
                    "type": "session",
                    "version": CURRENT_SESSION_VERSION,
                    "id": "s1",
                    "timestamp": "2026-01-01T00:00:00.000Z",
                    "cwd": "/x",
                }
            ]
        result = load_sqlite_marked_session_file(
            "sqlite:agent:s1:/store",
            load_events=load_events,
            options={"cwdOverride": "/override"},
        )
        assert result["cwd"] == "/override"

    def test_non_sqlite_marker_returns_none(self) -> None:
        def load_events(marker):
            return []
        assert (
            load_sqlite_marked_session_file(
                "/path/to/file.jsonl", load_events=load_events
            )
            is None
        )

    def test_short_sqlite_marker_returns_none(self) -> None:
        def load_events(marker):
            return []
        # Minimum form is ``sqlite:<agent>:<id>:<store>``
        # (4 parts).
        assert (
            load_sqlite_marked_session_file(
                "sqlite:agent:s1", load_events=load_events
            )
            is None
        )

    def test_missing_session_id_raises(self) -> None:
        def load_events(marker):
            return []
        with pytest.raises(RuntimeError, match="session id"):
            load_sqlite_marked_session_file(
                "sqlite:::store:scope", load_events=load_events
            )


# ── session_manager_file — recoverCorruptSessionEntries
# ──────────────────────


class TestRecoverCorruptSessionEntries:
    def test_recover_with_existing_header(self, tmp_path) -> None:
        """Mirrors ``recoverCorruptSessionEntries``
        (``session-manager-file.ts:530-555``)."""
        file_path = str(tmp_path / "corrupt.jsonl")
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(
                json.dumps(_v3_header(sid="recovered")) + "\n"
            )
            f.write(
                json.dumps(
                    {
                        "type": "message",
                        "id": "m1",
                        "parentId": None,
                        "timestamp": "2026-01-01T00:00:00.000Z",
                        "message": {"role": "user"},
                    }
                )
                + "\n"
            )
        # Snapshot the file content for the
        # backup-comparison check.
        original = open(file_path, "r", encoding="utf-8").read()
        recovered = recover_corrupt_session_entries(
            file_path, cwd="/recovered"
        )
        assert recovered is not None
        # The header was preserved.
        assert recovered[0]["id"] == "recovered"
        # The non-header entries are preserved.
        assert any(
            e.get("type") == "message" for e in recovered
        )
        # A backup was written.
        backup_files = [
            p for p in os.listdir(tmp_path)
            if p.startswith("corrupt.jsonl.corrupt-")
        ]
        assert len(backup_files) == 1
        # The backup content matches the original.
        backup_content = open(
            os.path.join(tmp_path, backup_files[0]),
            "r",
            encoding="utf-8",
        ).read()
        assert backup_content == original

    def test_recover_with_fresh_header(self, tmp_path) -> None:
        """When the file has no usable header, the
        recovery creates a fresh one."""
        file_path = str(tmp_path / "no_header.jsonl")
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    {
                        "type": "message",
                        "id": "m1",
                        "parentId": None,
                        "timestamp": "2026-01-01T00:00:00.000Z",
                        "message": {"role": "user"},
                    }
                )
                + "\n"
            )
        recovered = recover_corrupt_session_entries(
            file_path, cwd="/fresh"
        )
        assert recovered is not None
        # Fresh header was created with the
        # current version + the supplied cwd.
        assert recovered[0]["type"] == "session"
        assert recovered[0]["cwd"] == "/fresh"
        assert recovered[0]["version"] == CURRENT_SESSION_VERSION
        # The non-header entry is preserved.
        assert recovered[1]["type"] == "message"

    def test_recover_empty_file_returns_none(self, tmp_path) -> None:
        file_path = str(tmp_path / "empty.jsonl")
        open(file_path, "w", encoding="utf-8").close()
        assert (
            recover_corrupt_session_entries(
                file_path, cwd="/x"
            )
            is None
        )


# ── session_manager_file — JSON serialization
# ─────────────────────────────


class TestJsonSerializationCanRunUserCode:
    def test_primitive_returns_false(self) -> None:
        """Mirrors the early returns
        (``session-manager-file.ts:357-360``)."""
        assert json_serialization_can_run_user_code(1) is False
        assert json_serialization_can_run_user_code(1.5) is False
        assert json_serialization_can_run_user_code("hi") is False
        assert json_serialization_can_run_user_code(True) is False
        assert json_serialization_can_run_user_code(None) is False

    def test_plain_dict_returns_false(self) -> None:
        assert json_serialization_can_run_user_code({}) is False
        assert (
            json_serialization_can_run_user_code({"a": 1, "b": "x"})
            is False
        )

    def test_plain_list_returns_false(self) -> None:
        assert json_serialization_can_run_user_code([1, 2, 3]) is False
        assert (
            json_serialization_can_run_user_code([{"a": 1}, "x"])
            is False
        )

    def test_object_with_tojson_returns_true(self) -> None:
        """The OpenClaw source's
        ``descriptors.toJSON`` / ``prototype.toJSON``
        check returns True
        (``session-manager-file.ts:373-377``)."""
        class _HasToJSON:
            def toJSON(self):
                return {"x": 1}
        assert (
            json_serialization_can_run_user_code(_HasToJSON())
            is True
        )


# ── session_manager_file — messageSerializesOwnedValues
# ─────────────────────


class TestMessageSerializesOwnedValues:
    def test_tool_result_with_details(self) -> None:
        """Mirrors the ``role === "toolResult" &&
        hasOwnProperty("details")`` branch
        (``session-manager-file.ts:419-420``)."""
        msg = {
            "role": "toolResult",
            "content": [{"type": "text", "text": "r"}],
            "details": {"x": 1},
        }
        assert message_serializes_owned_values(msg) is True

    def test_tool_result_without_details(self) -> None:
        msg = {
            "role": "toolResult",
            "content": [{"type": "text", "text": "r"}],
        }
        assert message_serializes_owned_values(msg) is False

    def test_assistant_with_tool_call(self) -> None:
        msg = {
            "role": "assistant",
            "content": [
                {"type": "toolCall", "id": "c1", "name": "x", "arguments": {}},
            ],
        }
        assert message_serializes_owned_values(msg) is True

    def test_assistant_with_text_only(self) -> None:
        msg = {
            "role": "assistant",
            "content": [{"type": "text", "text": "hi"}],
        }
        assert message_serializes_owned_values(msg) is False

    def test_custom_with_details(self) -> None:
        msg = {
            "role": "custom",
            "content": "note",
            "details": {"k": "v"},
        }
        assert message_serializes_owned_values(msg) is True


# ── session_manager_file — rememberWrittenSessionEntries
# ────────────────────────


class TestRememberWrittenSessionEntries:
    def test_remembered_file_returns_snapshot(self, tmp_path) -> None:
        """Mirrors ``rememberWrittenSessionEntries``
        (``session-manager-file.ts:196-241``)."""
        file_path = str(tmp_path / "rem.jsonl")
        _write_session_file(file_path, _v3_header())
        result = remember_written_session_entries(file_path)
        assert result["snapshot"] is not None
        assert result["verifiedWrite"] is False
        assert result["stableRead"] is True

    def test_remembered_file_with_expected_content(
        self, tmp_path
    ) -> None:
        file_path = str(tmp_path / "rem.jsonl")
        _write_session_file(file_path, _v3_header())
        content = open(file_path, "r", encoding="utf-8").read()
        result = remember_written_session_entries(
            file_path, expected_content=content
        )
        assert result["verifiedWrite"] is True

    def test_remembered_file_with_mismatched_expected_content(
        self, tmp_path
    ) -> None:
        file_path = str(tmp_path / "rem.jsonl")
        _write_session_file(file_path, _v3_header())
        result = remember_written_session_entries(
            file_path, expected_content="wrong content"
        )
        assert result["verifiedWrite"] is False


# ── session_manager_file — rememberAppendedSessionEntry
# ──────────────────────


class TestRememberAppendedSessionEntry:
    def test_cache_advanced_for_known_snapshot(self, tmp_path) -> None:
        """Mirrors the cached-snapshot branch
        (``session-manager-file.ts:300-336``)."""
        file_path = str(tmp_path / "append.jsonl")
        _write_session_file(file_path, _v3_header())
        before_snapshot = read_session_file_snapshot(file_path)
        # ``verify`` first to populate the cache.
        remember_written_session_entries(file_path)
        # The OpenClaw source's append helper
        # expects ``cacheOwnedAppend: true`` and
        # is called *after* the actual file
        # append (the helper checks the file size
        # grew by the serialized-append length).
        serialized_append = (
            '\n{"type":"message","id":"m1",'
            '"parentId":null,"timestamp":"t",'
            '"message":{"role":"user"}}'
        )
        # The file is written in **binary** mode so
        # the on-disk byte length equals the
        # ``serializedAppend.encode("utf-8")``
        # length. Text mode on Windows converts
        # ``\n`` to ``\r\n`` which would
        # off-by-one the
        # ``remember_appended_session_entry``
        # size-growth check.
        with open(file_path, "ab") as f:
            f.write(serialized_append.encode("utf-8"))
        result = remember_appended_session_entry(
            {
                "file_path": file_path,
                "previousSnapshot": before_snapshot,
                "beforeAppendSnapshot": before_snapshot,
                "serializedAppend": serialized_append,
                "cacheOwnedAppend": True,
                "publishOwnedAppend": True,
                "invalidateSerializedPrefixCache": False,
            }
        )
        assert result["cacheAdvanced"] is True
        assert result["ownedAppendVerified"] is True

    def test_cache_disabled_returns_no_advance(
        self, tmp_path
    ) -> None:
        file_path = str(tmp_path / "append.jsonl")
        _write_session_file(file_path, _v3_header())
        before_snapshot = read_session_file_snapshot(file_path)
        result = remember_appended_session_entry(
            {
                "file_path": file_path,
                "previousSnapshot": before_snapshot,
                "beforeAppendSnapshot": before_snapshot,
                "serializedAppend": "\n{}",
                "cacheOwnedAppend": False,
                "publishOwnedAppend": True,
                "invalidateSerializedPrefixCache": False,
            }
        )
        assert result["cacheAdvanced"] is False


# ── session_manager_file — canPublishOwnedSessionAppend
# ─────────────────────


class TestCanPublishOwnedSessionAppend:
    def test_returns_true_with_snapshot(self) -> None:
        snap = SessionFileSnapshot(
            dev=1, ino=2, size=3, mtime_ns=4, ctime_ns=5
        )
        assert (
            can_publish_owned_session_append("file.jsonl", snap)
            is True
        )

    def test_returns_false_without_snapshot(self) -> None:
        assert (
            can_publish_owned_session_append("file.jsonl", None)
            is False
        )


# ── session_manager_file — publishRememberedSessionFileSnapshot
# ───────────────────


class TestPublishRememberedSessionFileSnapshot:
    def test_none_snapshot_is_noop(self) -> None:
        # ``None`` snapshot is a no-op
        # (``session-manager-file.ts:343-345``).
        publish_remembered_session_file_snapshot("x.jsonl", None)


# ── session_manager_list — findMostRecentSession
# ──────────────────────


class TestFindMostRecentSession:
    def test_no_directory_returns_none(self, tmp_path) -> None:
        assert (
            find_most_recent_session(str(tmp_path / "missing"))
            is None
        )

    def test_empty_directory_returns_none(self, tmp_path) -> None:
        d = tmp_path / "empty"
        d.mkdir()
        assert find_most_recent_session(str(d)) is None

    def test_returns_most_recent(self, tmp_path) -> None:
        """Mirrors ``findMostRecentSession``
        (``session-manager-list.ts:61-77``)."""
        d = tmp_path / "sessions"
        d.mkdir()
        # Two session files; the second is newer.
        old_path = d / "old.jsonl"
        new_path = d / "new.jsonl"
        _write_session_file(str(old_path), _v3_header(sid="old"))
        time.sleep(0.05)  # ensure mtime ordering
        _write_session_file(str(new_path), _v3_header(sid="new"))
        result = find_most_recent_session(str(d))
        assert result == str(new_path)

    def test_filters_by_cwd(self, tmp_path) -> None:
        d = tmp_path / "sessions"
        d.mkdir()
        # Two files, different cwds.
        a = d / "a.jsonl"
        b = d / "b.jsonl"
        _write_session_file(str(a), _v3_header(cwd="/cwd-a", sid="a"))
        time.sleep(0.05)
        _write_session_file(str(b), _v3_header(cwd="/cwd-b", sid="b"))
        # Filter to /cwd-a; only ``a.jsonl`` matches.
        result = find_most_recent_session(str(d), cwd="/cwd-a")
        assert result == str(a)


# ── session_manager_list — listSessions
# ──────────────────────────────


class TestListSessions:
    def test_empty_directory(self, tmp_path) -> None:
        d = tmp_path / "sessions"
        d.mkdir()
        sessions = asyncio.run(list_sessions("/cwd", str(d)))
        assert sessions == []

    def test_missing_directory(self, tmp_path) -> None:
        sessions = asyncio.run(
            list_sessions("/cwd", str(tmp_path / "missing"))
        )
        assert sessions == []

    def test_lists_sessions_for_cwd(self, tmp_path) -> None:
        """Mirrors ``listSessions``
        (``session-manager-list.ts:244-252``)."""
        d = tmp_path / "sessions"
        d.mkdir()
        # Two files for /my-cwd, one for another.
        a = d / "a.jsonl"
        b = d / "b.jsonl"
        c = d / "c.jsonl"
        _write_session_file(str(a), _v3_header(cwd="/my-cwd", sid="a"))
        time.sleep(0.01)
        _write_session_file(str(b), _v3_header(cwd="/my-cwd", sid="b"))
        time.sleep(0.01)
        _write_session_file(str(c), _v3_header(cwd="/other", sid="c"))
        sessions = asyncio.run(list_sessions("/my-cwd", str(d)))
        # Only ``a`` and ``b`` are listed; ``c`` is
        # filtered out.
        assert len(sessions) == 2
        ids = {s.id for s in sessions}
        assert ids == {"a", "b"}

    def test_progress_callback_invoked(self, tmp_path) -> None:
        d = tmp_path / "sessions"
        d.mkdir()
        a = d / "a.jsonl"
        _write_session_file(str(a), _v3_header(sid="a"))
        progress_calls: list = []
        asyncio.run(
            list_sessions(
                "/some/cwd",
                str(d),
                on_progress=lambda loaded, total: progress_calls.append(
                    (loaded, total)
                ),
            )
        )
        # The progress callback fires at least once.
        assert len(progress_calls) >= 1
        # The final call has loaded == total.
        assert progress_calls[-1][0] == progress_calls[-1][1]


# ── session_manager_list — listAllSessions
# ───────────────────────────────


class TestListAllSessions:
    def test_no_sessions_dir_returns_empty(self, tmp_path) -> None:
        # Point to a directory that doesn't exist.
        sessions = asyncio.run(list_all_sessions())
        # The default is ``~/.jarvis/.../sessions``
        # which probably doesn't exist in tests.
        # The function must not raise.
        assert isinstance(sessions, list)

    def test_walks_subdirs(self, tmp_path, monkeypatch) -> None:
        """Mirrors ``listAllSessions``
        (``session-manager-list.ts:254-296``)."""
        # Monkey-patch the sessions dir resolver.
        import src.agents.sessions.session_manager_list as sml
        monkeypatch.setattr(sml, "_sessions_dir_default", lambda: str(tmp_path))
        # Two sub-directories with one file each.
        d1 = tmp_path / "agent1"
        d2 = tmp_path / "agent2"
        d1.mkdir()
        d2.mkdir()
        _write_session_file(
            str(d1 / "a.jsonl"),
            _v3_header(cwd="/cwd1", sid="a"),
        )
        _write_session_file(
            str(d2 / "b.jsonl"),
            _v3_header(cwd="/cwd2", sid="b"),
        )
        sessions = asyncio.run(list_all_sessions())
        ids = {s.id for s in sessions}
        assert ids == {"a", "b"}


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
