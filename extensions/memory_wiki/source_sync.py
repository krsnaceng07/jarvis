"""source_sync — Memory Wiki source sync orchestrator (Phase 4.3f-mr3 stub).

OpenClaw parity: mirrors
``extensions/memory-wiki/src/source-sync.ts``.

The full implementation (which walks the
bridge / unsafe-local imports + calls
:func:`sync_memory_wiki_bridge_sources` /
:func:`sync_unsafe_local_sources` /
:func:`prune_imported_source_entries`) lands
in Phase 4.3g. Phase 4.3f-mr3 ships the
:func:`sync_memory_wiki_imported_sources`
stub so the ``sync_imported_sources_if_needed``
helper in :mod:`tool` is fully wired.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .config import ResolvedMemoryWikiConfig


@dataclass
class MemoryWikiSourceSyncResult:
    """The result of :func:`sync_memory_wiki_imported_sources`.

    Mirrors the OpenClaw
    ``SyncMemoryWikiImportedSourcesResult``
    shape (the deep counts are added in
    4.3g).
    """

    imported_count: int = 0
    updated_count: int = 0
    skipped_count: int = 0
    removed_count: int = 0


def sync_memory_wiki_imported_sources(
    *,
    config: ResolvedMemoryWikiConfig,
    app_config: Any = None,
) -> MemoryWikiSourceSyncResult:
    """Sync the imported sources (Phase 4.3f-mr3 stub).

    Returns a no-op
    :class:`MemoryWikiSourceSyncResult`. The
    full implementation lands in Phase 4.3g.
    """
    return MemoryWikiSourceSyncResult()


def reset_memory_wiki_source_sync_state_for_tests() -> None:
    """Reset module-level state (test-only helper)."""
    return


__all__ = [
    "MemoryWikiSourceSyncResult",
    "reset_memory_wiki_source_sync_state_for_tests",
    "sync_memory_wiki_imported_sources",
]
