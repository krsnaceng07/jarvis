"""Tests for ``jarvis_state_core.readonly``.

Covers:
- read-only handle lifecycle (open + close on exit)
- busy_timeout pragma applied
- schema-version refusal for newer-than-supported DBs
- legacy schemas (lower user_version) are tolerated
- the read-only handle cannot mutate the file
"""
from __future__ import annotations

import os
import sqlite3

import pytest

from jarvis_state_core.readonly import with_state_database_read_only


@pytest.fixture
def state_db_path(tmp_path, monkeypatch):
    """A custom-path SQLite file used when the test wants a
    specific filename.
    """
    db_path = tmp_path / "state.sqlite"
    db_path.touch()
    monkeypatch.setenv("JARVIS_STATE_DIR", str(tmp_path))
    return db_path


@pytest.fixture
def default_state_db_path(tmp_path, monkeypatch):
    """The canonical ``jarvis.sqlite`` file used when the test
    resolves the default state path.
    """
    db_path = tmp_path / "jarvis.sqlite"
    db_path.touch()
    monkeypatch.setenv("JARVIS_STATE_DIR", str(tmp_path))
    return db_path


def test_readonly_opens_and_closes(state_db_path):
    seen = []

    def op(handle):
        seen.append(handle)
        row = handle.db.execute("PRAGMA user_version").fetchone()
        assert row[0] == 0
        return "ok"

    result = with_state_database_read_only(op, path=str(state_db_path))
    assert result == "ok"
    assert seen and seen[0].path == os.path.abspath(str(state_db_path))


def test_readonly_applies_busy_timeout(state_db_path):
    captured = {}

    def op(handle):
        captured["busy_timeout"] = handle.db.execute(
            "PRAGMA busy_timeout"
        ).fetchone()[0]
        return None

    with_state_database_read_only(op, path=str(state_db_path))
    assert captured["busy_timeout"] == 5_000


def test_readonly_refuses_newer_schema(state_db_path, monkeypatch):
    monkeypatch.setattr(
        "jarvis_state_core.readonly.STATE_SCHEMA_VERSION", 1
    )
    conn = sqlite3.connect(str(state_db_path))
    conn.execute("PRAGMA user_version = 99")
    conn.commit()
    conn.close()

    def op(_handle):
        return "should-not-run"

    with pytest.raises(Exception) as info:
        with_state_database_read_only(op, path=str(state_db_path))
    assert "schema version" in str(info.value).lower()


def test_readonly_tolerates_legacy_schema(state_db_path):
    """A user_version below the current cap is fine (no error)."""
    conn = sqlite3.connect(str(state_db_path))
    conn.execute("PRAGMA user_version = 0")
    conn.commit()
    conn.close()

    def op(handle):
        return handle.db.execute("PRAGMA user_version").fetchone()[0]

    assert with_state_database_read_only(op, path=str(state_db_path)) == 0


def test_readonly_handle_cannot_mutate(state_db_path):
    """The read-only connection must reject any write attempt."""
    conn = sqlite3.connect(str(state_db_path))
    conn.execute("CREATE TABLE samples (n INTEGER)")
    conn.execute("INSERT INTO samples VALUES (1)")
    conn.commit()
    conn.close()

    def op(handle):
        with pytest.raises(sqlite3.OperationalError):
            handle.db.execute("INSERT INTO samples VALUES (2)")
        return handle.db.execute("SELECT n FROM samples").fetchall()

    rows = with_state_database_read_only(op, path=str(state_db_path))
    assert [dict(r)["n"] for r in rows] == [1]


def test_readonly_uses_explicit_path(state_db_path):
    seen = []

    def op(handle):
        seen.append(handle.path)
        return None

    with_state_database_read_only(op, path=str(state_db_path))
    assert seen[0] == os.path.abspath(str(state_db_path))


def test_readonly_uses_default_path_when_no_path(default_state_db_path):
    seen = []

    def op(handle):
        seen.append(handle.path)
        return None

    with_state_database_read_only(op)
    assert seen[0] == os.path.abspath(
        str(default_state_db_path)
    )


def test_readonly_opens_with_row_factory(state_db_path):
    # Seed with a writable connection first.
    seed = sqlite3.connect(str(state_db_path))
    seed.execute("CREATE TABLE x (n INTEGER)")
    seed.execute("INSERT INTO x VALUES (42)")
    seed.commit()
    seed.close()

    def op2(handle):
        return dict(handle.db.execute("SELECT * FROM x").fetchone())

    out = with_state_database_read_only(op2, path=str(state_db_path))
    assert out == {"n": 42}


def test_readonly_validates_callable():
    with pytest.raises(TypeError):
        with_state_database_read_only("not-callable")  # type: ignore[arg-type]
