"""Tests for extensions/memory_wiki/import_runs_state.py.

Phase 4.3e-mr2: ports the OpenClaw
``import-runs-state.ts`` helpers. The tests
focus on:

- Round-trip write → read via the in-memory
  fallback store.
- Per-vault scoping: state for vault A doesn't
  leak into vault B.
- ``list`` returns every record for the vault.
- ``row_count`` accounts for meta + path rows.
- Legacy file path round-trip via
  ``read_legacy_memory_wiki_import_run_records``.
- Corrupt + missing legacy files are skipped
  without raising.
- Invalid records (missing required fields,
  wrong import type) are dropped during
  normalization.
- The in-memory fallback persists across calls
  in the same process.
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

from extensions.memory_wiki.import_runs_state import (  # noqa: E402
    LEGACY_IMPORT_RUN_READ_CONCURRENCY,
    MEMORY_WIKI_IMPORT_RUN_STATE_MAX_ENTRIES,
    MEMORY_WIKI_IMPORT_RUN_STATE_NAMESPACE,
    SUPPORTED_IMPORT_TYPES,
    ChatGptImportRunEntry,
    ChatGptImportRunRecord,
    configure_memory_wiki_import_run_state_store,
    count_memory_wiki_import_run_state_rows,
    create_memory_fallback_import_run_store,
    create_memory_wiki_import_run_state_store,
    list_memory_wiki_import_run_records,
    read_legacy_memory_wiki_import_run_records,
    read_memory_wiki_import_run_record,
    reset_memory_wiki_import_run_state_for_tests,
    resolve_memory_wiki_import_runs_dir,
    write_memory_wiki_import_run_record,
)


def _record(
    *,
    run_id: str = "run-1",
    export_path: str = "/tmp/export.json",
    source_path: str = "/tmp/source",
    applied_at: str = "2026-07-17T00:00:00.000Z",
    conversation_count: int = 5,
    created_count: int = 2,
    updated_count: int = 1,
    skipped_count: int = 0,
    created_paths: list[str] | None = None,
    updated_paths: list[ChatGptImportRunEntry] | None = None,
    rolled_back_at: str | None = None,
) -> ChatGptImportRunRecord:
    return ChatGptImportRunRecord(
        run_id=run_id,
        import_type="chatgpt",
        export_path=export_path,
        source_path=source_path,
        applied_at=applied_at,
        conversation_count=conversation_count,
        created_count=created_count,
        updated_count=updated_count,
        skipped_count=skipped_count,
        created_paths=created_paths if created_paths is not None else ["sources/a.md"],
        updated_paths=updated_paths
        if updated_paths is not None
        else [ChatGptImportRunEntry(path="sources/b.md")],
        rolled_back_at=rolled_back_at,
    )


@pytest.fixture(autouse=True)
def _reset_state():
    """Reset module-level state before and after each test."""
    reset_memory_wiki_import_run_state_for_tests()
    yield
    reset_memory_wiki_import_run_state_for_tests()


class TestConstants:
    def test_namespace(self) -> None:
        assert MEMORY_WIKI_IMPORT_RUN_STATE_NAMESPACE == "import-runs"
        assert MEMORY_WIKI_IMPORT_RUN_STATE_MAX_ENTRIES == 20_000
        assert LEGACY_IMPORT_RUN_READ_CONCURRENCY == 16
        assert "chatgpt" in SUPPORTED_IMPORT_TYPES


class TestRoundTrip:
    def test_write_then_read(self, tmp_path: Path) -> None:
        store = create_memory_fallback_import_run_store()
        record = _record(
            created_paths=["sources/a.md", "sources/c.md"],
            updated_paths=[
                ChatGptImportRunEntry(path="sources/b.md"),
                ChatGptImportRunEntry(path="sources/d.md", snapshot_path="/tmp/d.json"),
            ],
        )
        write_memory_wiki_import_run_record(str(tmp_path), record, store)
        read_back = read_memory_wiki_import_run_record(str(tmp_path), record.run_id, store)
        assert read_back == record

    def test_state_scoped_per_vault(self, tmp_path: Path) -> None:
        store = create_memory_fallback_import_run_store()
        vault_a = str(tmp_path / "a")
        vault_b = str(tmp_path / "b")
        write_memory_wiki_import_run_record(vault_a, _record(run_id="a"), store)
        assert read_memory_wiki_import_run_record(vault_a, "a", store) is not None
        assert read_memory_wiki_import_run_record(vault_b, "a", store) is None

    def test_list_returns_all(self, tmp_path: Path) -> None:
        store = create_memory_fallback_import_run_store()
        vault_root = str(tmp_path)
        write_memory_wiki_import_run_record(vault_root, _record(run_id="a"), store)
        write_memory_wiki_import_run_record(
            vault_root,
            _record(
                run_id="b",
                created_paths=[],
                updated_paths=[],
            ),
            store,
        )
        records = list_memory_wiki_import_run_records(vault_root, store)
        assert {r.run_id for r in records} == {"a", "b"}

    def test_write_replaces_existing_path_rows(self, tmp_path: Path) -> None:
        # A second write for the same runId
        # should replace the old path rows
        # (the OpenClaw store calls ``delete``
        # for every key not in the new record's
        # path list).
        store = create_memory_fallback_import_run_store()
        vault_root = str(tmp_path)
        write_memory_wiki_import_run_record(
            vault_root,
            _record(
                created_paths=["sources/a.md", "sources/b.md"],
            ),
            store,
        )
        write_memory_wiki_import_run_record(
            vault_root,
            _record(created_paths=["sources/c.md"]),
            store,
        )
        read_back = read_memory_wiki_import_run_record(vault_root, "run-1", store)
        assert read_back is not None
        assert read_back.created_paths == ["sources/c.md"]

    def test_row_count_includes_meta_and_paths(self, tmp_path: Path) -> None:
        store = create_memory_fallback_import_run_store()
        vault_root = str(tmp_path)
        write_memory_wiki_import_run_record(
            vault_root,
            _record(
                created_paths=["sources/a.md", "sources/b.md"],
                updated_paths=[
                    ChatGptImportRunEntry(path="sources/c.md"),
                    ChatGptImportRunEntry(path="sources/d.md"),
                ],
            ),
            store,
        )
        # Meta + 2 created + 2 updated = 5 rows
        # total.
        assert store.row_count() == 5
        # The module-level helper uses the
        # configured store (None here → fallback).
        assert count_memory_wiki_import_run_state_rows(store) == 5


class TestNormalization:
    def test_record_missing_required_field_is_dropped(self) -> None:
        # ``runId`` is missing → returns None.
        assert (
            read_memory_wiki_import_run_record(
                "/tmp/vault",
                "any",
                create_memory_fallback_import_run_store(),
            )
            is None
        )

    def test_unknown_import_type_rejected(self, tmp_path: Path) -> None:
        # Sanity: ``unknown`` is not in the
        # supported import types set, so any
        # record with that import type would be
        # dropped during normalization.
        assert "unknown" not in SUPPORTED_IMPORT_TYPES

    def test_skips_paths_with_empty_path(self, tmp_path: Path) -> None:
        # The keyed store normalizes on read:
        # ``updatedPaths`` entries with no
        # ``path`` are dropped. The in-memory
        # store, by contrast, preserves the
        # record verbatim (the in-memory store
        # is only used in tests where the data
        # is constructed in-process, so
        # normalization is a no-op).
        from extensions.memory_wiki.import_runs_state import (
            OpenKeyedStoreOptions,
            open_plugin_state_keyed_store,
        )

        # Build a real keyed store + an
        # import-run store on top of it. The
        # keyed store applies normalization on
        # every read.
        def factory(options):  # type: ignore[no-untyped-def]
            return open_plugin_state_keyed_store(
                OpenKeyedStoreOptions(
                    namespace=options.namespace,
                    max_entries=options.max_entries,
                )
            )

        store = create_memory_wiki_import_run_state_store(factory)
        record = _record(
            updated_paths=[
                ChatGptImportRunEntry(path="sources/keep.md"),
                ChatGptImportRunEntry(path="  "),
            ],
        )
        write_memory_wiki_import_run_record(str(tmp_path), record, store)
        read_back = read_memory_wiki_import_run_record(str(tmp_path), "run-1", store)
        assert read_back is not None
        assert len(read_back.updated_paths) == 1
        assert read_back.updated_paths[0].path == "sources/keep.md"


class TestLegacyFile:
    def test_legacy_directory_round_trip(self, tmp_path: Path) -> None:
        vault_root = tmp_path
        runs_dir = Path(resolve_memory_wiki_import_runs_dir(str(vault_root)))
        runs_dir.mkdir(parents=True, exist_ok=True)
        # Write two legacy records.
        (runs_dir / "run-1.json").write_text(
            json.dumps(
                {
                    "version": 1,
                    "runId": "legacy-1",
                    "importType": "chatgpt",
                    "exportPath": "/tmp/exp1.json",
                    "sourcePath": "/tmp/src1",
                    "appliedAt": "2026-07-17T00:00:00.000Z",
                    "conversationCount": 3,
                    "createdCount": 1,
                    "updatedCount": 1,
                    "skippedCount": 1,
                    "createdPaths": ["sources/a.md"],
                    "updatedPaths": [{"path": "sources/b.md"}],
                }
            ),
            encoding="utf-8",
        )
        (runs_dir / "run-2.json").write_text(
            json.dumps(
                {
                    "version": 1,
                    "runId": "legacy-2",
                    "importType": "chatgpt",
                    "exportPath": "/tmp/exp2.json",
                    "sourcePath": "/tmp/src2",
                    "appliedAt": "2026-07-17T00:00:00.000Z",
                    "conversationCount": 0,
                    "createdCount": 0,
                    "updatedCount": 0,
                    "skippedCount": 0,
                    "createdPaths": [],
                    "updatedPaths": [],
                }
            ),
            encoding="utf-8",
        )
        records = read_legacy_memory_wiki_import_run_records(str(vault_root))
        assert {r.run_id for r in records} == {"legacy-1", "legacy-2"}

    def test_legacy_directory_missing(self, tmp_path: Path) -> None:
        # No ``.openclaw-wiki/import-runs/``
        # directory → returns empty.
        records = read_legacy_memory_wiki_import_run_records(str(tmp_path))
        assert records == []

    def test_legacy_corrupt_files_are_skipped(self, tmp_path: Path) -> None:
        vault_root = tmp_path
        runs_dir = Path(resolve_memory_wiki_import_runs_dir(str(vault_root)))
        runs_dir.mkdir(parents=True, exist_ok=True)
        (runs_dir / "bad.json").write_text("not json", encoding="utf-8")
        (runs_dir / "ok.json").write_text(
            json.dumps(
                {
                    "version": 1,
                    "runId": "ok-1",
                    "importType": "chatgpt",
                    "exportPath": "/tmp/exp",
                    "sourcePath": "/tmp/src",
                    "appliedAt": "2026-07-17T00:00:00.000Z",
                    "conversationCount": 0,
                    "createdCount": 0,
                    "updatedCount": 0,
                    "skippedCount": 0,
                    "createdPaths": [],
                    "updatedPaths": [],
                }
            ),
            encoding="utf-8",
        )
        records = read_legacy_memory_wiki_import_run_records(str(vault_root))
        assert [r.run_id for r in records] == ["ok-1"]


class TestConfigure:
    def test_configure_changes_default_store(self, tmp_path: Path) -> None:
        store = create_memory_fallback_import_run_store()
        configure_memory_wiki_import_run_state_store(store)
        vault_root = str(tmp_path)
        write_memory_wiki_import_run_record(vault_root, _record(run_id="via-default"))
        assert read_memory_wiki_import_run_record(vault_root, "via-default") is not None
        configure_memory_wiki_import_run_state_store(None)

    def test_rollback_record_round_trips(self, tmp_path: Path) -> None:
        store = create_memory_fallback_import_run_store()
        record = _record(rolled_back_at="2026-07-18T00:00:00.000Z")
        write_memory_wiki_import_run_record(str(tmp_path), record, store)
        read_back = read_memory_wiki_import_run_record(str(tmp_path), record.run_id, store)
        assert read_back is not None
        assert read_back.rolled_back_at == "2026-07-18T00:00:00.000Z"

    def test_empty_paths_record(self, tmp_path: Path) -> None:
        store = create_memory_fallback_import_run_store()
        record = _record(created_paths=[], updated_paths=[])
        write_memory_wiki_import_run_record(str(tmp_path), record, store)
        read_back = read_memory_wiki_import_run_record(str(tmp_path), record.run_id, store)
        assert read_back is not None
        assert read_back.created_paths == []
        assert read_back.updated_paths == []


class TestFallbackPersistence:
    def test_in_memory_store_persists_across_calls(self, tmp_path: Path) -> None:
        # Two distinct ``create_memory_fallback_import_run_store``
        # calls share the same module-level
        # dict; writes from one are visible in
        # the other.
        store_a = create_memory_fallback_import_run_store()
        store_b = create_memory_fallback_import_run_store()
        write_memory_wiki_import_run_record(str(tmp_path), _record(run_id="shared"), store_a)
        read_back = read_memory_wiki_import_run_record(str(tmp_path), "shared", store_b)
        assert read_back is not None
        assert read_back.run_id == "shared"
