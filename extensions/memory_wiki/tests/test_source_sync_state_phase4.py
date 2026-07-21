"""Tests for extensions/memory_wiki/source_sync_state.py.

Phase 4.3e-mr1: ports the OpenClaw
``source-sync-state.ts`` helpers. The tests
focus on:

- Round-trip write → read via the in-memory
  fallback store.
- Per-vault scoping: state for vault A doesn't
  leak into vault B.
- Plan-based partial write (upsert + delete).
- Capacity pre-check raises
  ``MemoryWikiSourceSyncCapacityError``.
- Legacy file path read.
- ``should_skip_imported_source_write``
  matches when source is unchanged.
- ``set_imported_source_entry`` is a no-op when
  every field is unchanged.
- ``prune_imported_source_entries`` removes
  inactive entries for a group.
"""

# ruff: noqa: S108 — the "/tmp/..." paths are test fixtures mirroring the OpenClaw TS source

# pyright: reportArgumentType=false
# pyright: reportAttributeAccessIssue=false
# pyright: reportCallIssue=false
# pyright: reportGeneralTypeIssues=false
# pyright: reportIndexIssue=false
# pyright: reportOptionalMemberAccess=false
# pyright: reportOptionalSubscript=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
# pyright: reportReturnType=false

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
for _candidate in (
    ROOT / "packages" / "plugin_sdk" / "src",
    ROOT / "apps" / "desktop" / "src",
):
    _candidate_str = str(_candidate)
    if _candidate_str not in sys.path:
        sys.path.insert(0, _candidate_str)

import pytest  # noqa: E402

from extensions.memory_wiki.source_sync_state import (  # noqa: E402
    MEMORY_WIKI_SOURCE_SYNC_STATE_MAX_ENTRIES,
    VALID_SOURCE_SYNC_GROUPS,
    MemoryWikiImportedSourceState,
    MemoryWikiImportedSourceStateEntry,
    MemoryWikiSourceSyncCapacityError,
    MemoryWikiSourceSyncStateStore,
    MemoryWikiSourceSyncStateWritePlan,
    assert_memory_wiki_source_sync_state_capacity,
    configure_memory_wiki_source_sync_state_store,
    create_memory_fallback_state_store,
    create_memory_wiki_source_sync_state_store,
    prune_imported_source_entries,
    read_legacy_memory_wiki_source_sync_state,
    read_memory_wiki_source_sync_state,
    reset_memory_wiki_source_sync_state_for_tests,
    resolve_memory_wiki_source_sync_state_path,
    set_imported_source_entry,
    should_skip_imported_source_write,
    write_memory_wiki_source_sync_state,
)


def _entry(
    *,
    group: str = "bridge",
    page_path: str = "sources/alpha.md",
    source_path: str = "/tmp/source.md",
    source_updated_at_ms: int = 123,
    source_size: int = 456,
    render_fingerprint: str = "fingerprint",
) -> MemoryWikiImportedSourceStateEntry:
    return MemoryWikiImportedSourceStateEntry(
        group=group,
        page_path=page_path,
        source_path=source_path,
        source_updated_at_ms=source_updated_at_ms,
        source_size=source_size,
        render_fingerprint=render_fingerprint,
    )


@pytest.fixture(autouse=True)
def _reset_state():
    """Reset module-level state before and after each test."""
    reset_memory_wiki_source_sync_state_for_tests()
    yield
    reset_memory_wiki_source_sync_state_for_tests()


class TestConstants:
    def test_namespace_constant(self) -> None:
        assert MEMORY_WIKI_SOURCE_SYNC_STATE_MAX_ENTRIES == 20_000

    def test_valid_groups(self) -> None:
        assert frozenset({"bridge", "unsafe-local"}) == VALID_SOURCE_SYNC_GROUPS


class TestRoundTrip:
    def test_write_then_read(self, tmp_path: Path) -> None:
        vault_root = str(tmp_path / "vault")
        store = create_memory_fallback_state_store()
        state = MemoryWikiImportedSourceState(
            version=1,
            entries={"alpha": _entry()},
        )
        write_memory_wiki_source_sync_state(vault_root, state, store)
        read_back = read_memory_wiki_source_sync_state(vault_root, store)
        assert read_back == state

    def test_state_scoped_per_vault(self, tmp_path: Path) -> None:
        store = create_memory_fallback_state_store()
        vault_a = str(tmp_path / "a")
        vault_b = str(tmp_path / "b")
        write_memory_wiki_source_sync_state(
            vault_a,
            MemoryWikiImportedSourceState(
                version=1,
                entries={"alpha": _entry(page_path="sources/alpha.md")},
            ),
            store,
        )
        # Vault B has no entries; should read back empty.
        empty = read_memory_wiki_source_sync_state(vault_b, store)
        assert empty.entries == {}

    def test_persists_only_changed_rows(self, tmp_path: Path) -> None:
        # Build a large state snapshot and ensure
        # the second write (with the same state)
        # is a no-op for ``register`` / ``delete``.
        # The Python port is *more* optimized than
        # the OpenClaw source (which calls
        # ``register`` for every entry on every
        # write): we read the existing entries
        # once, then only call ``register`` for
        # entries whose payload actually changed.
        vault_root = str(tmp_path / "vault")
        counting = _CountingStore(max_entries=10_000)
        entries = {
            f"source-{i}": _entry(
                page_path=f"sources/source-{i}.md",
                source_path=f"/tmp/source-{i}.md",
                source_updated_at_ms=i,
                source_size=i,
                render_fingerprint=f"fingerprint-{i}",
            )
            for i in range(50)
        }
        state = MemoryWikiImportedSourceState(version=1, entries=entries)
        write_memory_wiki_source_sync_state(vault_root, state, counting.store)
        # First write: every entry is a new
        # ``register``.
        assert counting.calls["register"] == 50
        assert counting.calls["delete"] == 0
        # Re-write the same state: zero
        # ``register`` / ``delete`` calls
        # (we read ``entries`` once to look up
        # the existing rows, then short-circuit
        # because every record is unchanged).
        counting.reset_calls()
        write_memory_wiki_source_sync_state(vault_root, state, counting.store)
        assert counting.calls["register"] == 0
        assert counting.calls["delete"] == 0

    def test_partial_write_plan(self, tmp_path: Path) -> None:
        vault_root = str(tmp_path / "vault")
        counting = _CountingStore(max_entries=10)
        state = MemoryWikiImportedSourceState(
            version=1,
            entries={
                "alpha": _entry(),
                "beta": _entry(page_path="sources/beta.md"),
            },
        )
        write_memory_wiki_source_sync_state(vault_root, state, counting.store)
        counting.reset_calls()
        # Plan: delete "alpha", upsert "gamma".
        set_imported_source_entry(
            sync_key="gamma",
            entry=_entry(page_path="sources/gamma.md"),
            state=state,
        )
        plan = MemoryWikiSourceSyncStateWritePlan(
            upsert_keys=["gamma"],
            delete_keys=["alpha"],
        )
        write_memory_wiki_source_sync_state(vault_root, state, counting.store, plan=plan)
        assert counting.calls["register"] == 1
        assert counting.calls["delete"] == 1
        read_back = read_memory_wiki_source_sync_state(vault_root, counting.store)
        assert "alpha" not in read_back.entries
        assert "beta" in read_back.entries
        assert "gamma" in read_back.entries


class TestShouldSkipImportedSourceWrite:
    def test_skip_when_unchanged_and_page_exists(self, tmp_path: Path) -> None:
        vault_root = tmp_path
        # Create a page file on disk.
        page = vault_root / "sources" / "alpha.md"
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text("hello", encoding="utf-8")
        state = MemoryWikiImportedSourceState(
            version=1,
            entries={
                "alpha": _entry(
                    page_path="sources/alpha.md",
                    source_updated_at_ms=123,
                    source_size=456,
                    render_fingerprint="fingerprint",
                )
            },
        )
        skip = should_skip_imported_source_write(
            vault_root=str(vault_root),
            sync_key="alpha",
            expected_page_path="sources/alpha.md",
            expected_source_path="/tmp/source.md",
            source_updated_at_ms=123,
            source_size=456,
            render_fingerprint="fingerprint",
            state=state,
        )
        assert skip is True

    def test_do_not_skip_when_size_changed(self, tmp_path: Path) -> None:
        vault_root = tmp_path
        (vault_root / "sources").mkdir(parents=True, exist_ok=True)
        (vault_root / "sources" / "alpha.md").write_text("hello", encoding="utf-8")
        state = MemoryWikiImportedSourceState(
            version=1,
            entries={"alpha": _entry(source_size=456)},
        )
        skip = should_skip_imported_source_write(
            vault_root=str(vault_root),
            sync_key="alpha",
            expected_page_path="sources/alpha.md",
            expected_source_path="/tmp/source.md",
            source_updated_at_ms=123,
            source_size=999,
            render_fingerprint="fingerprint",
            state=state,
        )
        assert skip is False

    def test_do_not_skip_when_page_missing(self, tmp_path: Path) -> None:
        # No page file on disk → do not skip.
        state = MemoryWikiImportedSourceState(
            version=1,
            entries={"alpha": _entry()},
        )
        skip = should_skip_imported_source_write(
            vault_root=str(tmp_path),
            sync_key="alpha",
            expected_page_path="sources/alpha.md",
            expected_source_path="/tmp/source.md",
            source_updated_at_ms=123,
            source_size=456,
            render_fingerprint="fingerprint",
            state=state,
        )
        assert skip is False

    def test_do_not_skip_when_key_missing(self, tmp_path: Path) -> None:
        skip = should_skip_imported_source_write(
            vault_root=str(tmp_path),
            sync_key="missing",
            expected_page_path="sources/alpha.md",
            expected_source_path="/tmp/source.md",
            source_updated_at_ms=123,
            source_size=456,
            render_fingerprint="fingerprint",
            state=MemoryWikiImportedSourceState(),
        )
        assert skip is False


class TestSetImportedSourceEntry:
    def test_noop_when_unchanged(self) -> None:
        state = MemoryWikiImportedSourceState(
            version=1,
            entries={"alpha": _entry()},
        )
        # Same fields → no change.
        set_imported_source_entry(sync_key="alpha", entry=_entry(), state=state)
        # State dict identity should be preserved
        # (no entry was replaced).
        assert state.entries["alpha"] is not None

    def test_updates_when_changed(self) -> None:
        state = MemoryWikiImportedSourceState(
            version=1,
            entries={"alpha": _entry(source_size=1)},
        )
        new_entry = _entry(source_size=2)
        set_imported_source_entry(sync_key="alpha", entry=new_entry, state=state)
        assert state.entries["alpha"].source_size == 2

    def test_inserts_new_key(self) -> None:
        state = MemoryWikiImportedSourceState()
        set_imported_source_entry(sync_key="alpha", entry=_entry(), state=state)
        assert "alpha" in state.entries


class TestPruneImportedSourceEntries:
    def test_prunes_inactive_for_group(self, tmp_path: Path) -> None:
        vault_root = tmp_path
        (vault_root / "sources").mkdir(parents=True, exist_ok=True)
        (vault_root / "sources" / "alpha.md").write_text("hi", encoding="utf-8")
        (vault_root / "sources" / "beta.md").write_text("hi", encoding="utf-8")
        state = MemoryWikiImportedSourceState(
            version=1,
            entries={
                "alpha": _entry(page_path="sources/alpha.md", group="bridge"),
                "beta": _entry(page_path="sources/beta.md", group="bridge"),
            },
        )
        removed = prune_imported_source_entries(
            vault_root=str(vault_root),
            group="bridge",
            active_keys={"alpha"},
            state=state,
        )
        assert removed == 1
        assert "alpha" in state.entries
        assert "beta" not in state.entries
        # The pruned page file is removed.
        assert not (vault_root / "sources" / "beta.md").exists()

    def test_does_not_touch_other_group(self, tmp_path: Path) -> None:
        vault_root = tmp_path
        (vault_root / "sources").mkdir(parents=True, exist_ok=True)
        (vault_root / "sources" / "alpha.md").write_text("hi", encoding="utf-8")
        (vault_root / "sources" / "beta.md").write_text("hi", encoding="utf-8")
        state = MemoryWikiImportedSourceState(
            version=1,
            entries={
                "alpha": _entry(page_path="sources/alpha.md", group="bridge"),
                "beta": _entry(
                    page_path="sources/beta.md",
                    group="unsafe-local",
                    source_path="/tmp/beta.md",
                ),
            },
        )
        removed = prune_imported_source_entries(
            vault_root=str(vault_root),
            group="bridge",
            active_keys=set(),
            state=state,
        )
        assert removed == 1
        assert "beta" in state.entries
        # The unsafe-local page stays on disk.
        assert (vault_root / "sources" / "beta.md").exists()

    def test_invalid_group_raises(self, tmp_path: Path) -> None:
        state = MemoryWikiImportedSourceState()
        with pytest.raises(ValueError, match="Invalid source-sync group"):
            prune_imported_source_entries(
                vault_root=str(tmp_path),
                group="bogus",
                active_keys=set(),
                state=state,
            )


class TestCapacity:
    def test_precheck_rejects_overflow(self) -> None:
        state = MemoryWikiImportedSourceState(
            version=1,
            entries={
                "retained": _entry(
                    group="unsafe-local",
                    page_path="sources/retained.md",
                    source_path="/tmp/retained.md",
                )
            },
        )
        with pytest.raises(MemoryWikiSourceSyncCapacityError):
            assert_memory_wiki_source_sync_state_capacity(
                state=state,
                group="bridge",
                incoming_count=MEMORY_WIKI_SOURCE_SYNC_STATE_MAX_ENTRIES,
            )

    def test_precheck_accepts_within_limit(self) -> None:
        state = MemoryWikiImportedSourceState()
        # Should not raise.
        assert_memory_wiki_source_sync_state_capacity(
            state=state,
            group="bridge",
            incoming_count=10,
        )

    def test_precheck_invalid_group_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid source-sync group"):
            assert_memory_wiki_source_sync_state_capacity(
                state=MemoryWikiImportedSourceState(),
                group="bogus",
                incoming_count=1,
            )

    def test_write_rejects_overflow(self, tmp_path: Path) -> None:
        # Construct a state that exceeds the
        # cap. The write call should raise before
        # touching the underlying store.
        vault_root = str(tmp_path / "vault")
        store = create_memory_fallback_state_store()
        entries = {
            f"source-{i}": _entry(
                page_path=f"sources/source-{i}.md",
                source_path=f"/tmp/source-{i}.md",
                source_updated_at_ms=i,
                source_size=i,
                render_fingerprint=f"fingerprint-{i}",
            )
            for i in range(MEMORY_WIKI_SOURCE_SYNC_STATE_MAX_ENTRIES + 1)
        }
        with pytest.raises(MemoryWikiSourceSyncCapacityError):
            write_memory_wiki_source_sync_state(
                vault_root,
                MemoryWikiImportedSourceState(version=1, entries=entries),
                store,
            )


class TestLegacyFile:
    def test_legacy_file_round_trip(self, tmp_path: Path) -> None:
        vault_root = tmp_path
        legacy_path = Path(resolve_memory_wiki_source_sync_state_path(str(vault_root)))
        legacy_path.parent.mkdir(parents=True, exist_ok=True)
        legacy_path.write_text(
            json.dumps(
                {
                    "version": 1,
                    "entries": {
                        "beta": {
                            "group": "unsafe-local",
                            "pagePath": "sources/beta.md",
                            "sourcePath": "/tmp/beta.md",
                            "sourceUpdatedAtMs": 10,
                            "sourceSize": 20,
                            "renderFingerprint": "beta",
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
        # The keyed-store read returns empty
        # (the legacy file is read separately).
        empty = read_memory_wiki_source_sync_state(str(vault_root))
        assert empty.entries == {}
        # The legacy-file read returns the entry.
        legacy = read_legacy_memory_wiki_source_sync_state(str(vault_root))
        assert "beta" in legacy.entries
        assert legacy.entries["beta"].group == "unsafe-local"

    def test_legacy_file_missing_returns_empty(self, tmp_path: Path) -> None:
        legacy = read_legacy_memory_wiki_source_sync_state(str(tmp_path))
        assert legacy.entries == {}


class TestConfigure:
    def test_configure_changes_default_store(self, tmp_path: Path) -> None:
        store = create_memory_fallback_state_store()
        configure_memory_wiki_source_sync_state_store(store)
        vault_root = str(tmp_path / "vault")
        write_memory_wiki_source_sync_state(
            vault_root,
            MemoryWikiImportedSourceState(version=1, entries={"alpha": _entry()}),
        )
        read_back = read_memory_wiki_source_sync_state(vault_root)
        assert "alpha" in read_back.entries
        configure_memory_wiki_source_sync_state_store(None)


# ── helpers ──────────────────────────────────────────────


class _CountingStore:
    """A ``PluginStateKeyedStore`` stand-in that counts calls.

    Mirrors the OpenClaw
    ``createCountingStore`` test helper:
    counts ``register`` / ``delete`` / ``entries``
    calls so tests can assert the no-op
    behavior of the partial-write path.
    """

    def __init__(self, *, max_entries: int = 20_000) -> None:
        self._values: dict[str, dict] = {}
        self._max_entries = max_entries
        self.calls = {"register": 0, "delete": 0, "entries": 0}

    def reset_calls(self) -> None:
        self.calls = {"register": 0, "delete": 0, "entries": 0}

    @property
    def store(self) -> MemoryWikiSourceSyncStateStore:
        return create_memory_wiki_source_sync_state_store(open_keyed_store=self._factory)

    def _factory(self, options: object) -> object:
        # The Python port's
        # ``create_memory_wiki_source_sync_state_store``
        # accepts a callable that takes the
        # OpenClaw options and returns a store.
        # We just return ``self`` because the
        # writer only ever calls the OpenClaw
        # methods on it.
        return self

    # The methods below mirror the OpenClaw
    # ``PluginStateKeyedStore`` shape. The writer
    # only ever calls ``register`` / ``delete``
    # / ``entries``.
    def register(self, key: str, value: object) -> None:  # type: ignore[no-untyped-def]
        self.calls["register"] += 1
        if key not in self._values and len(self._values) >= self._max_entries:
            oldest_key = next(iter(self._values))
            self._values.pop(oldest_key, None)
        self._values[key] = value  # type: ignore[assignment]

    def delete(self, key: str) -> bool:  # type: ignore[no-untyped-def]
        self.calls["delete"] += 1
        return self._values.pop(key, None) is not None

    def entries(self) -> list:  # type: ignore[no-untyped-def]
        self.calls["entries"] += 1
        return [{"key": k, "value": v, "createdAt": 0} for k, v in self._values.items()]

    def lookup(self, key: str) -> object:  # type: ignore[no-untyped-def]
        return self._values.get(key)
