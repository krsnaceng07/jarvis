"""source_sync — Memory Wiki source sync orchestrator (Phase 4.3g-mr2).

OpenClaw parity: mirrors
``extensions/memory-wiki/src/source-sync.ts``.

The orchestrator that dispatches a
source-sync run to either the bridge or
unsafe-local pipeline (depending on
``vaultMode``) and then refreshes the
vault indexes via
:func:`extensions.memory_wiki.compile_pipeline.compile_wiki_vault`.
Equivalent concurrent polls for the
same vault share the same in-flight
promise; the whole flight runs under the
vault mutation lock so it cannot
interleave with apply / compile /
ingest.
"""

# ruff: noqa: N815 — field names mirror the
# OpenClaw camelCase JSON shape so the
# gateway response is byte-compatible
# with the OpenClaw host.

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from .bridge import BridgeMemoryWikiResult, sync_memory_wiki_bridge_sources
from .compile_pipeline import compile_wiki_vault
from .mutation_coordinator import (
    resolve_memory_wiki_vault_mutation_key,
    with_memory_wiki_vault_mutation,
)

if TYPE_CHECKING:
    from .config import ResolvedMemoryWikiConfig


@dataclass(frozen=True, slots=True)
class MemoryWikiImportedSourceSyncResult:
    """The result of :func:`sync_memory_wiki_imported_sources`.

    Mirrors the OpenClaw
    ``MemoryWikiImportedSourceSyncResult``
    type. Field names are camelCase to
    match the OpenClaw JSON shape.
    """

    importedCount: int
    updatedCount: int
    skippedCount: int
    removedCount: int
    artifactCount: int
    workspaces: int
    pagePaths: list[str]
    indexesRefreshed: bool
    indexUpdatedFiles: list[str]
    indexRefreshReason: str


# Per-vault de-dup map. Mirrors the OpenClaw
# ``activeImportedSourceSyncs`` map (per
# vault mutation key).
_active_syncs: dict[str, list[dict[str, Any]]] = {}


def _resolve_request_key(
    *,
    config: ResolvedMemoryWikiConfig,
    vault_key: str,
) -> str:
    """Return a stable request key for the
    current (config, vault) tuple.

    Mirrors the OpenClaw
    ``resolveImportedSourceSyncRequestKey``
    helper. JSON-serializes the config
    with the vault path swapped for the
    normalized ``vault_key``.
    """
    import json

    return json.dumps(
        {**config.__dict__, "vault": {**config.vault.__dict__, "path": vault_key}},
        default=str,
        sort_keys=True,
    )


async def _sync_once(
    *,
    config: ResolvedMemoryWikiConfig,
    app_config: Any = None,
) -> MemoryWikiImportedSourceSyncResult:
    """The unlocked body.

    Mirrors the OpenClaw
    ``syncMemoryWikiImportedSourcesOnce``
    function.
    """
    if config.vaultMode == "bridge":
        sync_result: BridgeMemoryWikiResult = await sync_memory_wiki_bridge_sources(
            config=config, app_config=app_config
        )
    else:
        # Non-bridge vaultModes: no imported
        # sources to sync. Return a no-op
        # result. The unsafe-local path is
        # wired in Phase 4.3g-mr4.
        sync_result = BridgeMemoryWikiResult(
            imported_count=0,
            updated_count=0,
            skipped_count=0,
            removed_count=0,
            artifact_count=0,
            workspaces=0,
            page_paths=[],
        )

    compile_result = compile_wiki_vault(config)
    # The Python port's CompileWikiVaultResult
    # doesn't carry an ``updated_files`` list
    # (it ships the slim 4.3d-mr4 shape with
    # ``pages`` / ``ignored_paths`` /
    # ``invalid_paths``). Treat the post-sync
    # compile as a refresh whenever at least
    # one new file was added or any file was
    # changed by the sync (the caller can read
    # the returned ``indexUpdatedFiles`` for the
    # exact set).
    refreshed = bool(sync_result.imported_count or sync_result.updated_count)
    return MemoryWikiImportedSourceSyncResult(
        importedCount=sync_result.imported_count,
        updatedCount=sync_result.updated_count,
        skippedCount=sync_result.skipped_count,
        removedCount=sync_result.removed_count,
        artifactCount=sync_result.artifact_count,
        workspaces=sync_result.workspaces,
        pagePaths=list(sync_result.page_paths),
        indexesRefreshed=refreshed,
        indexUpdatedFiles=[p.relative_path for p in compile_result.pages],
        indexRefreshReason="compiled" if refreshed else "no-changes",
    )


async def sync_memory_wiki_imported_sources(
    *,
    config: ResolvedMemoryWikiConfig,
    app_config: Any = None,
) -> MemoryWikiImportedSourceSyncResult:
    """Sync the imported sources for ``config``.

    Mirrors the OpenClaw
    :func:`syncMemoryWikiImportedSources`.
    Equivalent concurrent polls share the
    same in-flight promise; the whole
    flight runs under the vault mutation
    lock.
    """
    vault_key = await resolve_memory_wiki_vault_mutation_key(config.vault.path)
    request_key = _resolve_request_key(config=config, vault_key=vault_key)
    active = _active_syncs.get(vault_key, [])
    for entry in active:
        if entry["requestKey"] == request_key and entry.get("appConfig") is app_config:
            return await entry["promise"]
    promise = with_memory_wiki_vault_mutation(
        config.vault.path,
        lambda: _sync_once(config=config, app_config=app_config),
    )
    new_entry: dict[str, Any] = {
        "requestKey": request_key,
        "promise": promise,
    }
    if app_config is not None:
        new_entry["appConfig"] = app_config
    active.append(new_entry)
    _active_syncs[vault_key] = active
    try:
        return await promise
    finally:
        active.remove(new_entry)
        if not active and _active_syncs.get(vault_key) is active:
            del _active_syncs[vault_key]


def reset_memory_wiki_source_sync_state_for_tests() -> None:
    """Reset module-level state (test-only helper)."""
    _active_syncs.clear()


__all__ = [
    "MemoryWikiImportedSourceSyncResult",
    "reset_memory_wiki_source_sync_state_for_tests",
    "sync_memory_wiki_imported_sources",
]
