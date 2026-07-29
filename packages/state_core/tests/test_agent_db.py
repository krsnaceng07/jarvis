"""Tests for ``jarvis_state_core.agent_db``.

Covers:
- default per-agent DB path layout
- open + close lifecycle
- busy_timeout pragma applied
- open reuses the cached handle
- close + reopen yields a fresh handle
- close_all + is_agent_database_open helpers
- inspect_agent_database_owner
"""
from __future__ import annotations

import os
import sqlite3
import threading

import pytest

from jarvis_state_core.agent_db import (
    close_agent_database,
    close_all_agent_databases,
    inspect_agent_database_owner,
    is_agent_database_open,
    open_agent_database,
    reset_agent_database_state_for_tests,
)


@pytest.fixture
def state_root(tmp_path, monkeypatch):
    root = tmp_path / "state"
    root.mkdir()
    monkeypatch.setenv("JARVIS_STATE_DIR", str(root))
    reset_agent_database_state_for_tests()
    yield root
    reset_agent_database_state_for_tests()


def test_default_path_layout(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_STATE_DIR", str(tmp_path / "s"))
    handle = open_agent_database({"agent_id": "main"})
    try:
        expected = os.path.join(
            os.path.abspath(str(tmp_path)),
            "agents",
            "main",
            "agent.sqlite",
        )
        assert handle.path == os.path.abspath(expected)
    finally:
        close_agent_database(handle.path)


def test_open_creates_file_and_parent_dir(state_root):
    handle = open_agent_database({"agent_id": "alpha"})
    try:
        assert os.path.isfile(handle.path)
        assert os.path.isdir(os.path.dirname(handle.path))
    finally:
        close_agent_database(handle.path)


def test_open_applies_busy_timeout(state_root):
    handle = open_agent_database({"agent_id": "bt"})
    try:
        row = handle.db.execute("PRAGMA busy_timeout").fetchone()
        assert row[0] == 5_000
    finally:
        close_agent_database(handle.path)


def test_open_reuses_cached_handle(state_root):
    handle_a = open_agent_database({"agent_id": "reuse"})
    handle_b = open_agent_database({"agent_id": "reuse"})
    try:
        assert handle_a.db is handle_b.db
    finally:
        close_agent_database(handle_a.path)


def test_open_rejects_conflicting_agent_id(state_root, tmp_path):
    """When the same path is opened for two different agent ids, refuse."""
    shared_path = tmp_path / "shared.sqlite"
    handle_a = open_agent_database(
        {"agent_id": "shared", "path": str(shared_path)}
    )
    try:
        with pytest.raises(RuntimeError):
            open_agent_database(
                {"agent_id": "different", "path": str(shared_path)}
            )
    finally:
        close_agent_database(handle_a.path)


def test_close_then_reopen_yields_fresh_handle(state_root):
    handle_a = open_agent_database({"agent_id": "fresh"})
    path = handle_a.path
    close_agent_database(path)
    handle_b = open_agent_database({"agent_id": "fresh"})
    try:
        assert handle_a.db is not handle_b.db
    finally:
        close_agent_database(handle_b.path)


def test_close_all_clears_cache(state_root):
    a = open_agent_database({"agent_id": "a"})
    b = open_agent_database({"agent_id": "b"})
    close_all_agent_databases()
    assert is_agent_database_open() is False
    assert is_agent_database_open(a.path) is False
    assert is_agent_database_open(b.path) is False


def test_is_agent_database_open_detects_active(state_root):
    handle = open_agent_database({"agent_id": "active"})
    try:
        assert is_agent_database_open() is True
        assert is_agent_database_open(handle.path) is True
        assert is_agent_database_open("does/not/exist") is False
    finally:
        close_agent_database(handle.path)


def test_open_with_explicit_path(state_root, tmp_path):
    custom = tmp_path / "custom.sqlite"
    handle = open_agent_database(
        {"agent_id": "any", "path": str(custom)}
    )
    try:
        assert handle.path == os.path.abspath(str(custom))
        assert os.path.isfile(handle.path)
    finally:
        close_agent_database(handle.path)


def test_open_with_explicit_factory(state_root):
    seen = []

    def factory() -> sqlite3.Connection:
        seen.append("called")
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        return conn

    handle = open_agent_database(
        {"agent_id": "factory", "connection_factory": factory}
    )
    try:
        assert seen == ["called"]
        # Path falls back to default even with custom factory.
        assert handle.path.endswith(
            os.path.join("factory", "agent.sqlite")
        )
    finally:
        close_agent_database(handle.path)


def test_open_rejects_empty_agent_id(state_root):
    with pytest.raises(ValueError):
        open_agent_database({"agent_id": "  "})


def test_open_rejects_non_dict_options(state_root):
    with pytest.raises(TypeError):
        open_agent_database("not-a-dict")  # type: ignore[arg-type]


def test_inspect_owned_reachable_file(state_root):
    handle = open_agent_database({"agent_id": "inspect"})
    try:
        result = inspect_agent_database_owner(handle.path)
        assert result.status in ("owned", "unowned")
    finally:
        close_agent_database(handle.path)


def test_inspect_unowned_missing_file(tmp_path):
    missing = tmp_path / "nope.sqlite"
    result = inspect_agent_database_owner(str(missing))
    assert result.status == "unowned"


def test_inspect_unreadable_corrupt_file(tmp_path, monkeypatch):
    """A file that isn't a SQLite DB reports ``unreadable``."""
    bad = tmp_path / "bad.sqlite"
    bad.write_bytes(b"not a sqlite file")
    result = inspect_agent_database_owner(str(bad))
    assert result.status in ("unreadable", "unowned")


def test_concurrent_opens(state_root):
    """Two threads open the same agent DB; both see the same handle."""
    handle_box: list = []
    errors: list = []
    barrier = threading.Barrier(2)

    def open_once() -> None:
        try:
            barrier.wait(timeout=2)
            handle = open_agent_database({"agent_id": "concurrent"})
            handle_box.append(handle)
        except Exception as error:  # noqa: BLE001
            errors.append(error)

    threads = [threading.Thread(target=open_once) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    try:
        assert not errors
        assert len(handle_box) == 2
        assert handle_box[0].db is handle_box[1].db
    finally:
        for h in handle_box:
            close_agent_database(h.path)
