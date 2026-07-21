"""chatgpt_import — Memory Wiki ChatGPT export import (Phase 4.3g-mr3 stub).

OpenClaw parity: mirrors
``extensions/memory-wiki/src/chatgpt-import.ts``.

The full ChatGPT import pipeline walks
the JSON export, maps every conversation
to one or more wiki source pages, runs
the per-run state store, and recompiles
the vault. The full port lands in
Phase 4.3g-mr3.

This module ships the public surface
shape + a no-op default implementation
so the gateway + tool layers can be
fully wired while the per-conversation
walk is finalized in the same phase.
"""

# ruff: noqa: N815 — field names mirror the
# OpenClaw camelCase JSON shape so the
# ``wiki.bridge.import`` /
# ``wiki.ingest`` gateway response is
# byte-compatible with the OpenClaw host.

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .config import ResolvedMemoryWikiConfig


@dataclass(frozen=True, slots=True)
class ChatGptImportResult:
    """The result of :func:`import_chatgpt_export`.

    Mirrors the OpenClaw
    ``ChatGptImportResult`` type. All
    field names are camelCase.
    """

    runId: str
    importType: str
    exportPath: str
    sourcePath: str
    appliedAt: str
    conversationCount: int
    createdCount: int
    updatedCount: int
    skippedCount: int
    pagePaths: list[str] = field(default_factory=list)


def reset_memory_wiki_chatgpt_import_state_for_tests() -> None:
    """Reset module-level state (test-only helper)."""
    return


async def import_chatgpt_export(
    config: ResolvedMemoryWikiConfig,
    *,
    export_path: str,
    app_config: Any = None,
    now_ms: int | None = None,
) -> ChatGptImportResult:
    """Import a ChatGPT JSON export into the
    wiki vault.

    The full implementation walks every
    conversation in ``export_path``,
    normalizes the mapping / current-
    branch / dream signals into wiki
    source pages, writes them through
    :func:`write_imported_source_page`,
    and records the run in the import-runs
    state store.

    For now, the surface is a no-op stub
    so the gateway / tool layers can be
    fully wired. The full port lands in
    the rest of Phase 4.3g-mr3.
    """
    return ChatGptImportResult(
        runId="",
        importType="chatgpt",
        exportPath=export_path,
        sourcePath="",
        appliedAt="",
        conversationCount=0,
        createdCount=0,
        updatedCount=0,
        skippedCount=0,
        pagePaths=[],
    )


__all__ = [
    "ChatGptImportResult",
    "import_chatgpt_export",
    "reset_memory_wiki_chatgpt_import_state_for_tests",
]
