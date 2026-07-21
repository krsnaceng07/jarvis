"""Tests for extensions/memory_wiki/doctor_contract.py.

Phase 4.3g-mr7: ports the OpenClaw
``doctor-contract-api.ts`` test surface.
The tests focus on:

- ``STATE_MIGRATIONS`` exposes 3
  contracts with the expected OpenClaw
  ids.
- ``register_memory_wiki_doctor_contracts``
  delegates to
  ``api.register_doctor_contract`` for
  every contract.
- Hosts without
  ``register_doctor_contract`` are a
  silent no-op.
- The compiled-cache cleanup contract
  detects + removes legacy cache files.
- The source-sync migration contract
  migrates ``source-sync.json`` into
  the keyed store + archives the legacy
  file.
- The import-runs migration contract
  migrates ``import-runs/*.json`` into
  the keyed store + archives the legacy
  files.
- Per-vault scope is respected: the
  contracts only touch configured vault
  roots.
"""

# ruff: noqa: S108 — test fixtures mirror the OpenClaw TS source

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

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
for _candidate in (
    ROOT / "packages" / "plugin_sdk" / "src",
    ROOT / "apps" / "desktop" / "src",
):
    _candidate_str = str(_candidate)
    if _candidate_str not in sys.path:
        sys.path.insert(0, _candidate_str)

import pytest  # noqa: E402

from extensions.memory_wiki.doctor_contract import (  # noqa: E402
    STATE_MIGRATIONS,
    register_memory_wiki_doctor_contracts,
)
from extensions.memory_wiki.import_runs_state import (  # noqa: E402
    reset_memory_wiki_import_run_state_for_tests,
)
from extensions.memory_wiki.source_sync_state import (  # noqa: E402
    read_memory_wiki_source_sync_state,
    reset_memory_wiki_source_sync_state_for_tests,
)


class _RecordingApi:
    """A minimal PluginApi stand-in that
    records the registered doctor
    contracts."""

    def __init__(self) -> None:
        self.contracts: list = []

    def register_doctor_contract(self, contract) -> None:
        self.contracts.append(contract)


class _NoHookApi:
    """An api stand-in that does NOT
    expose ``register_doctor_contract``."""


@pytest.fixture(autouse=True)
def _reset_state():
    """Reset module-level state before
    and after each test."""
    reset_memory_wiki_source_sync_state_for_tests()
    reset_memory_wiki_import_run_state_for_tests()
    yield
    reset_memory_wiki_source_sync_state_for_tests()
    reset_memory_wiki_import_run_state_for_tests()


def _migration_by_id(migration_id: str) -> dict[str, Any]:
    for contract in STATE_MIGRATIONS:
        if contract["id"] == migration_id:
            return contract
    raise AssertionError(f"Missing migration {migration_id!r}")


def _config_with_vault(
    *, vault_path: str, state_dir: Path, agent_ids: list[str] | None = None
) -> dict[str, Any]:
    """Build a full app config that
    :func:`_resolve_configured_vault_roots`
    understands.
    """
    cfg: dict[str, Any] = {
        "plugins": {
            "entries": {
                "memory-wiki": {
                    "config": {
                        "vault": {
                            "path": vault_path,
                        }
                    }
                }
            }
        }
    }
    if agent_ids:
        cfg["agents"] = {"list": [{"id": agent_id} for agent_id in agent_ids]}
    return cfg


class TestExports:
    def test_three_migrations(self) -> None:
        assert len(STATE_MIGRATIONS) == 3
        ids = {c["id"] for c in STATE_MIGRATIONS}
        assert ids == {
            "memory-wiki-compiled-cache-file-cleanup",
            "memory-wiki-source-sync-json-to-plugin-state",
            "memory-wiki-import-runs-json-to-plugin-state",
        }

    def test_each_migration_has_detect_and_apply(self) -> None:
        for contract in STATE_MIGRATIONS:
            assert callable(contract["detect"])
            assert callable(contract["apply"])
            assert "id" in contract
            assert "label" in contract
            assert "version" in contract


class TestRegister:
    def test_registers_each_contract(self) -> None:
        api = _RecordingApi()
        register_memory_wiki_doctor_contracts(api)
        assert len(api.contracts) == 3
        assert api.contracts == STATE_MIGRATIONS

    def test_noop_on_hosts_without_register(self) -> None:
        # No exception when the api
        # doesn't expose the registration
        # method.
        register_memory_wiki_doctor_contracts(_NoHookApi())


def _path_in_lines(path: Path, lines: list[str]) -> bool:
    """Return True iff ``str(path)`` (forward
    slashes on Windows) appears in any of
    ``lines`` after normalization to
    forward slashes.
    """
    target = str(path).replace("\\", "/")
    return any(target in line.replace("\\", "/") for line in lines)


def _in_memory_keyed_store_factory(*_args, **_kwargs):
    """An ``openKeyedStore`` factory stub for
    tests. Accepts the
    :class:`OpenKeyedStoreOptions` kwargs
    the doctor contract passes (which
    ``create_memory_fallback_state_store``
    doesn't accept) and returns the
    in-memory keyed store (the *inner*
    store, not the wiki wrapper). The
    doctor contract wraps it via
    :func:`create_memory_wiki_source_sync_state_store`
    (or
    :func:`create_memory_wiki_import_run_state_store`).
    """
    from extensions.memory_wiki.import_runs_state import (
        _default_keyed_store_factory as _inner_import_runs,
    )
    from extensions.memory_wiki.source_sync_state import (
        _default_keyed_store_factory as _inner_source_sync,
    )

    # Both keyed stores use the same
    # in-memory plugin-state keyed store
    # under the hood; either factory will
    # do for the test.
    _ = _inner_import_runs  # silence unused
    return _inner_source_sync()


class TestCompiledCacheCleanup:
    def test_detects_and_removes_legacy_cache_files(self, tmp_path: Path) -> None:
        vault = tmp_path / "vault"
        cache_dir = vault / ".openclaw-wiki" / "cache"
        cache_dir.mkdir(parents=True)
        legacy_files = [
            cache_dir / "agent-digest.json",
            cache_dir / "claims.jsonl",
        ]
        for file_path in legacy_files:
            file_path.write_text("stale\n", encoding="utf-8")

        contract = _migration_by_id("memory-wiki-compiled-cache-file-cleanup")
        params = {
            "config": _config_with_vault(vault_path=str(vault), state_dir=tmp_path),
            "env": {},
        }
        preview = asyncio.run(contract["detect"](params))
        assert preview is not None
        for file_path in legacy_files:
            assert _path_in_lines(
                file_path, preview.preview
            ), f"Expected preview to mention {file_path}, got {preview.preview}"

        result = asyncio.run(contract["apply"](params))
        for file_path in legacy_files:
            assert _path_in_lines(file_path, result.changes)
        # Files are gone.
        for file_path in legacy_files:
            assert not file_path.exists()

    def test_skips_missing_vault(self, tmp_path: Path) -> None:
        contract = _migration_by_id("memory-wiki-compiled-cache-file-cleanup")
        params = {
            "config": _config_with_vault(
                vault_path=str(tmp_path / "missing-vault"),
                state_dir=tmp_path,
            ),
            "env": {},
        }
        preview = asyncio.run(contract["detect"](params))
        assert preview is None
        result = asyncio.run(contract["apply"](params))
        assert result.changes == []
        assert result.warnings == []


class TestSourceSyncMigration:
    def test_migrates_legacy_file(self, tmp_path: Path) -> None:
        vault = tmp_path / "vault"
        legacy_path = vault / ".openclaw-wiki" / "source-sync.json"
        legacy_path.parent.mkdir(parents=True, exist_ok=True)
        legacy_path.write_text(
            json.dumps(
                {
                    "version": 1,
                    "entries": {
                        "alpha": {
                            "group": "bridge",
                            "pagePath": "sources/alpha.md",
                            "sourcePath": "/tmp/alpha.md",
                            "sourceUpdatedAtMs": 100,
                            "sourceSize": 200,
                            "renderFingerprint": "alpha",
                        }
                    },
                }
            ),
            encoding="utf-8",
        )

        contract = _migration_by_id("memory-wiki-source-sync-json-to-plugin-state")
        params = {
            "config": _config_with_vault(vault_path=str(vault), state_dir=tmp_path),
            "env": {},
            "context": {"openPluginStateKeyedStore": (_in_memory_keyed_store_factory)},
        }
        preview = asyncio.run(contract["detect"](params))
        assert preview is not None
        assert any("Memory Wiki source sync" in line for line in preview.preview)

        result = asyncio.run(contract["apply"](params))
        # At least one change line should
        # mention the migration.
        assert any("Migrated Memory Wiki source sync" in change for change in result.changes)
        # The legacy file is archived.
        assert not legacy_path.exists()
        assert (vault / ".openclaw-wiki" / "source-sync.json.migrated").exists()
        # The keyed store contains the
        # entry.
        read_back = read_memory_wiki_source_sync_state(str(vault))
        assert "alpha" in read_back.entries


class TestImportRunsMigration:
    def test_migrates_legacy_records(self, tmp_path: Path) -> None:
        vault = tmp_path / "vault"
        runs_dir = vault / ".openclaw-wiki" / "import-runs"
        runs_dir.mkdir(parents=True)
        run_path = runs_dir / "alpha-run.json"
        run_path.write_text(
            json.dumps(
                {
                    "version": 1,
                    "runId": "alpha-run",
                    "importType": "chatgpt",
                    "exportPath": "/tmp/alpha",
                    "sourcePath": "/tmp/alpha-source",
                    "appliedAt": "2026-07-21T00:00:00Z",
                    "conversationCount": 0,
                    "createdCount": 0,
                    "updatedCount": 0,
                    "skippedCount": 0,
                    "createdPaths": [],
                    "updatedPaths": [],
                    "pagePaths": [],
                }
            ),
            encoding="utf-8",
        )

        contract = _migration_by_id("memory-wiki-import-runs-json-to-plugin-state")
        params = {
            "config": _config_with_vault(vault_path=str(vault), state_dir=tmp_path),
            "env": {},
            "context": {"openPluginStateKeyedStore": (_in_memory_keyed_store_factory)},
        }
        preview = asyncio.run(contract["detect"](params))
        assert preview is not None
        assert any("Memory Wiki import runs" in line for line in preview.preview)

        result = asyncio.run(contract["apply"](params))
        assert any("Migrated Memory Wiki import runs" in change for change in result.changes)
        # Legacy file is archived.
        assert not run_path.exists()
        assert os.path.exists(run_path.with_suffix(".json.migrated"))
