"""doctor_contract — Memory Wiki doctor state migrations (Phase 4.3g-mr7).

OpenClaw parity: mirrors
``extensions/memory-wiki/doctor-contract-api.ts``.

The memory-wiki plugin owns three
state-migration contracts that the
host's ``doctor`` command runs to find
and rewrite legacy plugin state:

1. ``memory-wiki-compiled-cache-file-cleanup``
   — remove rebuildable legacy cache
   files (``.openclaw-wiki/cache/agent-digest.json``,
   ``.openclaw-wiki/cache/claims.jsonl``)
   that are no longer needed because
   the compiled-cache store replaces
   them.
2. ``memory-wiki-source-sync-json-to-plugin-state``
   — migrate the legacy
   ``.openclaw-wiki/source-sync.json``
   state file into the host's
   plugin-state keyed store (the
   keyed store is the canonical
   persistence layer from 4.3e-mr1).
3. ``memory-wiki-import-runs-json-to-plugin-state``
   — migrate the legacy per-run
   ``.openclaw-wiki/import-runs/*.json``
   records into the host's
   plugin-state keyed store.

Each contract is a plain dict (the
shape :class:`PluginApi.register_doctor_contract`
consumes); the host invokes
``detectLegacyState({...})`` to find
candidate paths + ``migrateLegacyState({...})``
to actually rewrite them.
"""

# ruff: noqa: N815, PLR0912, PLR0915, ASYNC230, RUF005 — camelCase
# field names mirror the OpenClaw JSON
# shape; the migration ladders mirror
# OpenClaw's exhaustive 3-migration
# state; the file reads are bounded
# (small JSON state files) and run
# inside the doctor contract, which
# is already serialized by the host.
# RUF005: the two ``warnings + [...]``
# concatenations are explicit
# ``(default + error)`` merges; a
# tuple-unpack refactor would be
# cosmetic churn.

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from .compiled_cache import LEGACY_MEMORY_WIKI_COMPILED_CACHE_PATHS
from .config import (
    resolve_memory_wiki_agent_config,
    resolve_memory_wiki_config,
    resolve_memory_wiki_configured_agent_ids,
)
from .import_runs_state import (
    count_memory_wiki_import_run_state_rows,
    create_memory_wiki_import_run_state_store,
    list_memory_wiki_import_run_records,
    read_legacy_memory_wiki_import_run_records,
    resolve_memory_wiki_import_runs_dir,
    write_memory_wiki_import_run_record,
)
from .source_sync_state import (
    MEMORY_WIKI_SOURCE_SYNC_STATE_MAX_ENTRIES,
    create_memory_wiki_source_sync_state_store,
    read_legacy_memory_wiki_source_sync_state,
    resolve_memory_wiki_source_sync_state_path,
    write_memory_wiki_source_sync_state,
)

if TYPE_CHECKING:
    from . import PluginApi


# ── Doctor migration contract shape ───────────────────────


@dataclass(frozen=True, slots=True)
class _DoctorPreview:
    """The human-readable preview for a
    candidate migration target.

    Mirrors OpenClaw's ``{preview: string[]}``
    contract return shape (the Python SDK
    flattens it into a list of strings).
    """

    preview: list[str]


@dataclass(frozen=True, slots=True)
class _DoctorApplyResult:
    """The result of running a migration.

    Mirrors OpenClaw's
    ``{changes: string[], warnings: string[]}``
    contract return shape.
    """

    changes: list[str]
    warnings: list[str]


# ── Helpers ────────────────────────────────────────────────


def _resolve_home_dir(env: dict[str, str]) -> str | None:
    """Return the home directory from
    ``env`` (``HOME`` on Unix,
    ``USERPROFILE`` on Windows).
    """
    home = env.get("HOME", "").strip()
    if home:
        return home
    user_profile = env.get("USERPROFILE", "").strip()
    return user_profile or None


def _read_configured_plugin_config(config: Any) -> dict[str, Any] | None:
    """Read the memory-wiki plugin config
    block from the host app config.

    Mirrors OpenClaw's
    ``readConfiguredPluginConfig``.
    Returns ``None`` if the config is
    malformed.
    """
    if not isinstance(config, dict):
        return None
    entries = (
        config.get("plugins", {}).get("entries", {})
        if isinstance(config.get("plugins"), dict)
        else None
    )
    if not isinstance(entries, dict):
        return None
    plugin_entry = entries.get("memory-wiki")
    if not isinstance(plugin_entry, dict):
        return None
    plugin_config = plugin_entry.get("config")
    if not isinstance(plugin_config, dict):
        return None
    return plugin_config


def _resolve_configured_vault_roots(config: Any, env: dict[str, str]) -> list[str]:
    """Resolve the list of configured
    vault roots.

    Mirrors OpenClaw's
    ``resolveConfiguredVaultRoots``.
    """
    plugin_config = _read_configured_plugin_config(config)
    resolved = resolve_memory_wiki_config(plugin_config, homedir=_resolve_home_dir(env))
    if resolved.vault.scope == "global":
        return [resolved.vault.path]
    configured_agent_ids = resolve_memory_wiki_configured_agent_ids(config)
    if not isinstance(configured_agent_ids, list):
        return []
    return [
        resolve_memory_wiki_agent_config(
            config=resolved,
            app_config=config,
            agent_id=agent_id,
        ).vault.path
        for agent_id in configured_agent_ids
    ]


def _safe_legacy_cache_file_exists(vault_root: str, relative_path: str) -> bool:
    """Return True iff ``relative_path``
    exists as a regular file under
    ``vault_root``.

    Mirrors OpenClaw's
    ``safeLegacyCacheFileExists`` —
    tolerates a missing vault root.
    """
    full_path = os.path.join(vault_root, relative_path)
    return os.path.isfile(full_path)


def _safe_legacy_state_file_exists(file_path: str) -> bool:
    """Return True iff ``file_path`` exists
    and is a regular file.

    Mirrors OpenClaw's
    ``legacyStateFileExists``.
    """
    return os.path.isfile(file_path)


def _archive_legacy_state_source(
    file_path: str,
    *,
    label: str,
    changes: list[str],
    warnings: list[str],
) -> None:
    """Move ``file_path`` to a sidecar
    ``.migrated`` path + record the
    change.

    Mirrors OpenClaw's
    ``archiveLegacyStateSource``. The
    Python port just renames the file
    (no journaling subsystem exists
    in our SDK yet); failures are
    silently logged into ``warnings``
    so the doctor can still report
    a successful migration.
    """
    try:
        os.rename(file_path, f"{file_path}.migrated")
    except OSError as exc:
        warnings.append(f"Failed to archive {label} at {file_path}: {exc}")
        return
    changes.append(f"Archived {label} legacy source -> {file_path}.migrated")


def _archive_legacy_import_run_records(
    vault_root: str, changes: list[str], warnings: list[str]
) -> None:
    """Archive every ``*.json`` legacy
    import-run record under
    ``.openclaw-wiki/import-runs/``.

    Mirrors OpenClaw's
    ``archiveLegacyImportRunRecords``.
    """
    import_runs_dir = resolve_memory_wiki_import_runs_dir(vault_root)
    if not os.path.isdir(import_runs_dir):
        return
    for entry in sorted(os.listdir(import_runs_dir)):
        if not entry.endswith(".json"):
            continue
        file_path = os.path.join(import_runs_dir, entry)
        if not os.path.isfile(file_path):
            continue
        _archive_legacy_state_source(
            file_path,
            label="Memory Wiki import-run",
            changes=changes,
            warnings=warnings,
        )


# ── Migration contracts ────────────────────────────────────


def _build_compiled_cache_cleanup_contract() -> dict[str, Any]:
    """Build the
    ``memory-wiki-compiled-cache-file-cleanup``
    doctor contract.

    Mirrors OpenClaw's first migration.
    """
    legacy_paths = list(LEGACY_MEMORY_WIKI_COMPILED_CACHE_PATHS)

    async def detect_legacy_state(params: dict[str, Any]) -> _DoctorPreview | None:
        previews: list[str] = []
        for vault_root in _resolve_configured_vault_roots(
            params.get("config"), params.get("env", {})
        ):
            if not os.path.isdir(vault_root):
                continue
            stale_paths = [
                os.path.join(vault_root, rel)
                for rel in legacy_paths
                if _safe_legacy_cache_file_exists(vault_root, rel)
            ]
            for file_path in stale_paths:
                previews.append(f"- Remove rebuildable Memory Wiki compiled cache: {file_path}")
        return _DoctorPreview(preview=previews) if previews else None

    async def migrate_legacy_state(params: dict[str, Any]) -> _DoctorApplyResult:
        changes: list[str] = []
        warnings: list[str] = []
        for vault_root in _resolve_configured_vault_roots(
            params.get("config"), params.get("env", {})
        ):
            if not os.path.isdir(vault_root):
                continue
            for rel in legacy_paths:
                full_path = os.path.join(vault_root, rel)
                if not _safe_legacy_cache_file_exists(vault_root, rel):
                    continue
                try:
                    os.remove(full_path)
                except OSError as exc:
                    warnings.append(
                        f"Failed removing rebuildable Memory Wiki compiled cache {full_path}: {exc}"
                    )
                    continue
                changes.append(f"Removed rebuildable Memory Wiki compiled cache: {full_path}")
        return _DoctorApplyResult(changes=changes, warnings=warnings)

    return {
        "id": "memory-wiki-compiled-cache-file-cleanup",
        "version": 1,
        "label": "Memory Wiki compiled cache files",
        "detect": detect_legacy_state,
        "apply": migrate_legacy_state,
    }


def _build_source_sync_migration_contract() -> dict[str, Any]:
    """Build the
    ``memory-wiki-source-sync-json-to-plugin-state``
    doctor contract.

    Mirrors OpenClaw's second migration.
    """

    async def detect_legacy_state(params: dict[str, Any]) -> _DoctorPreview | None:
        previews: list[str] = []
        for vault_root in _resolve_configured_vault_roots(
            params.get("config"), params.get("env", {})
        ):
            legacy_path = resolve_memory_wiki_source_sync_state_path(vault_root)
            state = read_legacy_memory_wiki_source_sync_state(vault_root)
            count = len(state.entries)
            if count == 0 or not _safe_legacy_state_file_exists(legacy_path):
                continue
            previews.append(
                f"- Memory Wiki source sync: {legacy_path} -> plugin state "
                f"(source-sync, {count} entries)"
            )
        return _DoctorPreview(preview=previews) if previews else None

    async def migrate_legacy_state(params: dict[str, Any]) -> _DoctorApplyResult:
        changes: list[str] = []
        warnings: list[str] = []
        open_keyed_store = params.get("context", {}).get("openPluginStateKeyedStore")
        if not callable(open_keyed_store):
            return _DoctorApplyResult(
                changes=changes,
                warnings=warnings
                + [
                    "Missing context.openPluginStateKeyedStore for memory-wiki source sync migration."
                ],
            )
        # The host's ``openPluginStateKeyedStore``
        # factory returns the inner keyed
        # store (a ``PluginStateKeyedStore``);
        # the doctor contract wraps it in a
        # ``MemoryWikiSourceSyncStateStore`` so
        # the rest of the wiki plugin can
        # read / write the source-sync state
        # uniformly.
        store = create_memory_wiki_source_sync_state_store(open_keyed_store)
        for vault_root in _resolve_configured_vault_roots(
            params.get("config"), params.get("env", {})
        ):
            legacy_path = resolve_memory_wiki_source_sync_state_path(vault_root)
            if not _safe_legacy_state_file_exists(legacy_path):
                continue
            state = read_legacy_memory_wiki_source_sync_state(vault_root)
            count = len(state.entries)
            if count == 0:
                continue
            existing_state = store.read(vault_root)
            merged_entries: dict[str, Any] = {
                **state.entries,
                **existing_state.entries,
            }
            merged_count = len(merged_entries)
            if merged_count > MEMORY_WIKI_SOURCE_SYNC_STATE_MAX_ENTRIES:
                warnings.append(
                    f"Skipped Memory Wiki source-sync import for {vault_root}: "
                    f"{merged_count} entries exceeds "
                    f"{MEMORY_WIKI_SOURCE_SYNC_STATE_MAX_ENTRIES}"
                )
                continue
            from .source_sync_state import MemoryWikiImportedSourceState

            merged_state = MemoryWikiImportedSourceState(version=1, entries=merged_entries)
            write_memory_wiki_source_sync_state(vault_root, merged_state, store)
            existing_count = len(existing_state.entries)
            imported_count = merged_count - existing_count
            changes.append(
                f"Migrated Memory Wiki source sync -> plugin state "
                f"({imported_count} imported, {existing_count} existing)"
            )
            _archive_legacy_state_source(
                legacy_path,
                label="Memory Wiki source-sync",
                changes=changes,
                warnings=warnings,
            )
        return _DoctorApplyResult(changes=changes, warnings=warnings)

    return {
        "id": "memory-wiki-source-sync-json-to-plugin-state",
        "version": 1,
        "label": "Memory Wiki source sync state",
        "detect": detect_legacy_state,
        "apply": migrate_legacy_state,
    }


def _build_import_runs_migration_contract() -> dict[str, Any]:
    """Build the
    ``memory-wiki-import-runs-json-to-plugin-state``
    doctor contract.

    Mirrors OpenClaw's third migration.
    """

    async def detect_legacy_state(params: dict[str, Any]) -> _DoctorPreview | None:
        previews: list[str] = []
        for vault_root in _resolve_configured_vault_roots(
            params.get("config"), params.get("env", {})
        ):
            records = read_legacy_memory_wiki_import_run_records(vault_root)
            if not records:
                continue
            previews.append(
                f"- Memory Wiki import runs: "
                f"{resolve_memory_wiki_import_runs_dir(vault_root)}/*.json "
                f"-> plugin state ({len(records)} records)"
            )
        return _DoctorPreview(preview=previews) if previews else None

    async def migrate_legacy_state(params: dict[str, Any]) -> _DoctorApplyResult:
        changes: list[str] = []
        warnings: list[str] = []
        open_keyed_store = params.get("context", {}).get("openPluginStateKeyedStore")
        if not callable(open_keyed_store):
            return _DoctorApplyResult(
                changes=changes,
                warnings=warnings
                + [
                    "Missing context.openPluginStateKeyedStore for memory-wiki import-runs migration."
                ],
            )
        store = create_memory_wiki_import_run_state_store(open_keyed_store)
        for vault_root in _resolve_configured_vault_roots(
            params.get("config"), params.get("env", {})
        ):
            records = read_legacy_memory_wiki_import_run_records(vault_root)
            if not records:
                continue
            existing_records = list_memory_wiki_import_run_records(vault_root, store)
            existing_run_ids = {getattr(record, "run_id", "") for record in existing_records}
            imported_records = [
                record
                for record in records
                if getattr(record, "run_id", "") not in existing_run_ids
            ]
            try:
                existing_row_count = count_memory_wiki_import_run_state_rows(store)
            except Exception as exc:
                warnings.append(f"Failed to count existing import-run state rows: {exc}")
                existing_row_count = 0
            # 1 + createdPaths + updatedPaths per
            # record is the per-record row
            # contribution (mirrors OpenClaw's
            # ``countImportRunStateRows``).
            projected_row_count = existing_row_count + sum(
                1
                + len(getattr(record, "created_paths", []))
                + len(getattr(record, "updated_paths", []))
                for record in imported_records
            )
            if projected_row_count > 50_000:
                warnings.append(
                    f"Skipped Memory Wiki import-run import for {vault_root}: "
                    f"{projected_row_count} state rows exceeds 50000"
                )
                continue
            imported_count = 0
            for record in imported_records:
                try:
                    write_memory_wiki_import_run_record(vault_root, record, store)
                    imported_count += 1
                except Exception as exc:
                    warnings.append(
                        f"Failed to import Memory Wiki import-run "
                        f"{getattr(record, 'run_id', '?')}: {exc}"
                    )
            changes.append(
                f"Migrated Memory Wiki import runs -> plugin state "
                f"({imported_count} imported, {len(existing_run_ids)} existing)"
            )
            _archive_legacy_import_run_records(vault_root, changes, warnings)
        return _DoctorApplyResult(changes=changes, warnings=warnings)

    return {
        "id": "memory-wiki-import-runs-json-to-plugin-state",
        "version": 1,
        "label": "Memory Wiki import run records",
        "detect": detect_legacy_state,
        "apply": migrate_legacy_state,
    }


# ── The three state-migration contracts ────────────────────


STATE_MIGRATIONS: list[dict[str, Any]] = [
    _build_compiled_cache_cleanup_contract(),
    _build_source_sync_migration_contract(),
    _build_import_runs_migration_contract(),
]


# ── Public surface ─────────────────────────────────────────


def register_memory_wiki_doctor_contracts(api: PluginApi) -> None:
    """Register the three memory-wiki
    doctor state-migration contracts on
    the host.

    Mirrors OpenClaw's
    ``doctor-contract-api.ts``
    ``stateMigrations`` export. The host
    invokes ``register_doctor_contract``
    for each contract; the doctor command
    then runs ``detect`` + ``apply`` for
    every plugin.

    Idempotent: calling it twice with the
    same ``api`` is a no-op (the host's
    doctor-contract registry dedupes by
    contract ``id``).
    """
    register = getattr(api, "register_doctor_contract", None)
    if not callable(register):
        # Older hosts don't expose
        # ``registerDoctorContract``;
        # skip the registration silently.
        return
    for contract in STATE_MIGRATIONS:
        register(contract)


__all__ = [
    "STATE_MIGRATIONS",
    "register_memory_wiki_doctor_contracts",
]
