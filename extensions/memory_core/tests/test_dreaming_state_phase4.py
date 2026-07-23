"""Tests for memory_core.dreaming_state — OpenClaw dreaming-state parity.

Mirrors the TypeScript ``test_dreaming-shared.test.ts`` and
``test_dreaming.test.ts`` patterns (only the state-store subset). The
in-memory keyed store is the same one used in
``tests/test_query_phase4.py`` (a dict-backed stand-in for the SDK's
real SQLite-backed store).
"""
from __future__ import annotations

from typing import Any

from extensions.memory_core import dreaming_state as ds


# ── In-memory keyed store (mirrors what the SDK's real store exposes) ───


class InMemoryKeyedStore:
    """Dict-backed stand-in for ``PluginStateKeyedStore``."""

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    def entries(self) -> list[tuple[str, Any]]:
        return list(self._data.items())

    def register(self, key: str, value: Any) -> None:
        self._data[key] = value

    def delete(self, key: str) -> None:
        self._data.pop(key, None)

    def clear(self) -> None:
        self._data.clear()


def _wire_store() -> InMemoryKeyedStore:
    store = InMemoryKeyedStore()
    ds.configure_memory_core_dreaming_state(
        lambda opts: store  # type: ignore[return-value]
    )
    return store


# ── Tests ─────────────────────────────────────────────────────────────────


def test_seven_namespaces_match_opencrypt() -> None:
    """All 7 namespace constants match OpenClaw's source exactly."""
    assert ds.DREAMING_DAILY_INGESTION_NAMESPACE == "dreaming-daily-ingestion"
    assert ds.DREAMING_SESSION_INGESTION_FILES_NAMESPACE == (
        "dreaming-session-ingestion-files"
    )
    assert ds.DREAMING_SESSION_INGESTION_SEEN_NAMESPACE == (
        "dreaming-session-ingestion-seen"
    )
    assert ds.SHORT_TERM_RECALL_NAMESPACE == "short-term-recall"
    assert ds.SHORT_TERM_PHASE_SIGNAL_NAMESPACE == "short-term-phase-signals"
    assert ds.SHORT_TERM_META_NAMESPACE == "short-term-meta"
    assert ds.SHORT_TERM_LOCK_NAMESPACE == "short-term-locks"


def test_capacity_constants() -> None:
    assert ds.SHORT_TERM_LOCK_MAX_ENTRIES == 4_096
    assert ds.SESSION_SEEN_HASHES_PER_CHUNK == 512


def test_normalize_workspace_key_windows_lowercases() -> None:
    key = ds.normalize_memory_core_workspace_key(r"E:\OpenClaw\Main")
    # On Windows the path is lowercased; on POSIX it's left as-is.
    if __import__("sys").platform == "win32":
        assert key == "e:/openclaw/main"
    else:
        assert key == "/E:\\OpenClaw\\Main" or key.endswith("/E:\\OpenClaw\\Main")


def test_normalize_workspace_key_replaces_backslashes() -> None:
    key = ds.normalize_memory_core_workspace_key("/foo/bar")
    assert "\\" not in key


def test_workspace_state_key_is_sha256_hex() -> None:
    key = ds.memory_core_workspace_state_key("/some/workspace")
    assert len(key) == 64
    int(key, 16)  # raises if not hex


def test_workspace_state_key_is_deterministic() -> None:
    a = ds.memory_core_workspace_state_key("/workspace/a")
    b = ds.memory_core_workspace_state_key("/workspace/a")
    assert a == b


def test_workspace_state_key_different_inputs_differ() -> None:
    a = ds.memory_core_workspace_state_key("/workspace/a")
    b = ds.memory_core_workspace_state_key("/workspace/b")
    assert a != b


def test_workspace_entry_key_format() -> None:
    key = ds.memory_core_workspace_entry_key("/workspace/a", "recall/2024-01-01")
    parts = key.split(":")
    assert len(parts) == 2
    assert parts[0] == ds.memory_core_workspace_state_key("/workspace/a")
    assert len(parts[1]) == 64


def test_state_reference_format() -> None:
    ref = ds.memory_core_state_reference(
        ds.SHORT_TERM_RECALL_NAMESPACE, "/workspace/a"
    )
    expected_workspace = ds.memory_core_workspace_state_key("/workspace/a")
    assert ref == f"plugin-state:memory-core/{ds.SHORT_TERM_RECALL_NAMESPACE}/{expected_workspace}"


def test_open_store_requires_configuration() -> None:
    # Reset the configured store.
    ds._configured_open_keyed_store = None  # noqa: SLF001 (test setup)
    raised = False
    try:
        ds.open_memory_core_state_store(ds.OpenKeyedStoreOptions(namespace="x"))
    except RuntimeError as e:
        raised = "not configured" in str(e)
    assert raised, "expected RuntimeError when not configured"
    # Restore.
    _wire_store()


def test_write_then_read_entries() -> None:
    _wire_store()
    ds.write_memory_core_workspace_entries(
        ds.SHORT_TERM_RECALL_NAMESPACE,
        "/workspace/a",
        [
            ("k1", {"v": 1}),
            ("k2", {"v": 2}),
        ],
    )
    entries = ds.read_memory_core_workspace_entries(
        ds.SHORT_TERM_RECALL_NAMESPACE, "/workspace/a"
    )
    assert sorted(k for k, _ in entries) == ["k1", "k2"]
    assert dict(entries) == {"k1": {"v": 1}, "k2": {"v": 2}}


def test_write_entries_prunes_stale() -> None:
    """Replace-set pattern: writes prune any key not in the new set."""
    _wire_store()
    ds.write_memory_core_workspace_entries(
        ds.SHORT_TERM_RECALL_NAMESPACE,
        "/workspace/a",
        [("k1", {"v": 1}), ("k2", {"v": 2}), ("k3", {"v": 3})],
    )
    # Now write only k1 + k3; k2 should be pruned.
    ds.write_memory_core_workspace_entries(
        ds.SHORT_TERM_RECALL_NAMESPACE,
        "/workspace/a",
        [("k1", {"v": 10}), ("k3", {"v": 30})],
    )
    entries = ds.read_memory_core_workspace_entries(
        ds.SHORT_TERM_RECALL_NAMESPACE, "/workspace/a"
    )
    assert sorted(k for k, _ in entries) == ["k1", "k3"]
    assert dict(entries) == {"k1": {"v": 10}, "k3": {"v": 30}}


def test_write_single_entry_does_not_prune() -> None:
    """``write_memory_core_workspace_entry`` is additive only."""
    _wire_store()
    ds.write_memory_core_workspace_entry(
        ds.SHORT_TERM_RECALL_NAMESPACE, "/workspace/a", "k1", {"v": 1}
    )
    ds.write_memory_core_workspace_entry(
        ds.SHORT_TERM_RECALL_NAMESPACE, "/workspace/a", "k2", {"v": 2}
    )
    entries = ds.read_memory_core_workspace_entries(
        ds.SHORT_TERM_RECALL_NAMESPACE, "/workspace/a"
    )
    assert sorted(k for k, _ in entries) == ["k1", "k2"]


def test_clear_workspace_namespace() -> None:
    _wire_store()
    ds.write_memory_core_workspace_entries(
        ds.SHORT_TERM_RECALL_NAMESPACE,
        "/workspace/a",
        [("k1", {"v": 1}), ("k2", {"v": 2})],
    )
    ds.clear_memory_core_workspace_namespace(
        ds.SHORT_TERM_RECALL_NAMESPACE, "/workspace/a"
    )
    entries = ds.read_memory_core_workspace_entries(
        ds.SHORT_TERM_RECALL_NAMESPACE, "/workspace/a"
    )
    assert entries == []


def test_workspaces_isolated_by_state_key() -> None:
    """Two workspaces must not see each other's entries."""
    _wire_store()
    ds.write_memory_core_workspace_entries(
        ds.SHORT_TERM_RECALL_NAMESPACE, "/workspace/a", [("shared", {"v": "A"})]
    )
    ds.write_memory_core_workspace_entries(
        ds.SHORT_TERM_RECALL_NAMESPACE, "/workspace/b", [("shared", {"v": "B"})]
    )
    a = ds.read_memory_core_workspace_entries(
        ds.SHORT_TERM_RECALL_NAMESPACE, "/workspace/a"
    )
    b = ds.read_memory_core_workspace_entries(
        ds.SHORT_TERM_RECALL_NAMESPACE, "/workspace/b"
    )
    assert dict(a) == {"shared": {"v": "A"}}
    assert dict(b) == {"shared": {"v": "B"}}


def test_clear_only_affects_target_workspace() -> None:
    _wire_store()
    ds.write_memory_core_workspace_entries(
        ds.SHORT_TERM_RECALL_NAMESPACE, "/workspace/a", [("k", {"v": "A"})]
    )
    ds.write_memory_core_workspace_entries(
        ds.SHORT_TERM_RECALL_NAMESPACE, "/workspace/b", [("k", {"v": "B"})]
    )
    ds.clear_memory_core_workspace_namespace(
        ds.SHORT_TERM_RECALL_NAMESPACE, "/workspace/a"
    )
    a = ds.read_memory_core_workspace_entries(
        ds.SHORT_TERM_RECALL_NAMESPACE, "/workspace/a"
    )
    b = ds.read_memory_core_workspace_entries(
        ds.SHORT_TERM_RECALL_NAMESPACE, "/workspace/b"
    )
    assert a == []
    assert dict(b) == {"k": {"v": "B"}}


def test_envelope_carries_workspace_key_for_defensive_filter() -> None:
    """The WorkspaceValue envelope must carry workspaceKey so reads can
    defensively filter even if the keyed store returns cross-workspace keys.
    """
    _wire_store()
    # Manually inject a foreign-workspace entry with the wrong workspaceKey
    # in its envelope — it should be filtered out by the defensive check.
    store = InMemoryKeyedStore()
    ds._configured_open_keyed_store = lambda opts: store  # noqa: SLF001
    ws_key_a = ds.memory_core_workspace_state_key("/workspace/a")
    ws_key_b = ds.memory_core_workspace_state_key("/workspace/b")
    state_key = ds.memory_core_workspace_entry_key("/workspace/a", "k")
    store.register(
        state_key,
        {
            "version": 1,
            "workspaceKey": ws_key_b,  # WRONG: belongs to b
            "workspaceDir": "/workspace/a",
            "key": "k",
            "value": {"should": "be_filtered"},
        },
    )
    entries = ds.read_memory_core_workspace_entries(
        ds.SHORT_TERM_RECALL_NAMESPACE, "/workspace/a"
    )
    assert entries == []  # defensively filtered
    # The store still has the entry (no auto-cleanup in read).
    assert len(store.entries()) == 1
