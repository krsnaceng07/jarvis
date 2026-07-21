"""unsafe_local — Memory Wiki unsafe-local source import (Phase 4.3g-mr4).

OpenClaw parity: mirrors
``extensions/memory-wiki/src/unsafe-local.ts``.

The unsafe-local import pipeline walks
every ``unsafeLocal.paths`` entry under
``vaultMode="unsafe-local"`` +
``allowPrivateMemoryCoreAccess=true``,
and writes a ``source.memory-unsafe-local``
page per discovered text file. The
source-sync state store tracks the
``syncKey → (configuredPath, sourcePath,
size, renderFingerprint)`` mapping so
re-runs skip unchanged files. Files
whose configured scope is no longer
readable are NOT pruned (the human
notes on those pages are preserved
until the scope is mounted again or
explicitly removed from config).
"""

# ruff: noqa: N815, PLR0915, ASYNC230, S324 — field names mirror the
# OpenClaw camelCase JSON shape; the
# per-artifact walk + fingerprint + page
# path computation mirrors OpenClaw's
# exhaustive ladder; the file reads are
# bounded (small text / json / yaml) and
# run inside an already-serialized vault
# mutation; SHA-1 fingerprint is
# OpenClaw's choice (stable short digest).

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from datetime import UTC
from typing import TYPE_CHECKING, Any

from .bridge import BridgeMemoryWikiResult
from .log import append_memory_wiki_log
from .markdown_pages import (
    create_wiki_page_filename,
    render_wiki_markdown,
    slugify_wiki_segment,
)
from .source_page_shared import write_imported_source_page
from .source_path_shared import resolve_artifact_key
from .source_sync_state import (
    assert_memory_wiki_source_sync_state_capacity,
    is_source_within_configured_path,
    prune_imported_source_entries,
    read_memory_wiki_source_sync_state,
    write_memory_wiki_source_sync_state,
)
from .vault import initialize_memory_wiki_vault

if TYPE_CHECKING:
    from .config import ResolvedMemoryWikiConfig


# Mirrors the OpenClaw
# ``DIRECTORY_TEXT_EXTENSIONS`` set.
DIRECTORY_TEXT_EXTENSIONS: frozenset[str] = frozenset(
    {".json", ".jsonl", ".md", ".txt", ".yaml", ".yml"}
)

# Mirrors the OpenClaw
# ``UNSAFE_LOCAL_SYNC_CONCURRENCY = 16``
# constant.
UNSAFE_LOCAL_SYNC_CONCURRENCY = 16


@dataclass(frozen=True, slots=True)
class UnsafeLocalArtifact:
    """A single unsafe-local artifact.

    Mirrors the OpenClaw ``UnsafeLocalArtifact``
    type. Field names are camelCase.
    """

    syncKey: str
    configuredPath: str
    absolutePath: str
    relativePath: str


@dataclass(frozen=True, slots=True)
class UnsafeLocalArtifactCollection:
    """The result of collecting unsafe-local
    artifacts from every configured path.

    Mirrors the OpenClaw
    ``UnsafeLocalArtifactCollection`` type.
    """

    artifacts: list[UnsafeLocalArtifact]
    unavailableConfiguredPaths: list[str]


def detect_fence_language(file_path: str) -> str:
    """Return the markdown fence language for
    ``file_path`` based on its extension.

    Mirrors the OpenClaw
    ``detectFenceLanguage`` helper.
    """
    ext = os.path.splitext(file_path)[1].lower()
    if ext in (".json", ".jsonl"):
        return "json"
    if ext in (".yaml", ".yml"):
        return "yaml"
    if ext == ".txt":
        return "text"
    return "markdown"


def _list_allowed_files_recursive(root_dir: str) -> list[str]:
    """Recursively list every file under
    ``root_dir`` whose extension is in
    :data:`DIRECTORY_TEXT_EXTENSIONS`,
    sorted by path.

    Mirrors the OpenClaw
    ``listAllowedFilesRecursive`` helper.
    """
    files: list[str] = []
    for entry in os.listdir(root_dir):
        full_path = os.path.join(root_dir, entry)
        if os.path.isdir(full_path):
            files.extend(_list_allowed_files_recursive(full_path))
        elif os.path.isfile(full_path):
            ext = os.path.splitext(entry)[1].lower()
            if ext in DIRECTORY_TEXT_EXTENSIONS:
                files.append(full_path)
    files.sort()
    return files


def collect_unsafe_local_artifacts(
    configured_paths: list[str],
) -> UnsafeLocalArtifactCollection:
    """Walk every configured path and collect
    the unsafe-local artifacts.

    Mirrors the OpenClaw
    ``collectUnsafeLocalArtifacts`` helper.
    """
    artifacts: list[UnsafeLocalArtifact] = []
    unavailable: list[str] = []
    for configured_path in configured_paths:
        absolute_configured_path = os.path.abspath(configured_path)
        scoped: list[UnsafeLocalArtifact] = []
        try:
            os.stat(absolute_configured_path)
        except OSError:
            unavailable.append(absolute_configured_path)
            continue
        if os.path.isdir(absolute_configured_path):
            for absolute_path in _list_allowed_files_recursive(absolute_configured_path):
                scoped.append(
                    UnsafeLocalArtifact(
                        syncKey=resolve_artifact_key(absolute_path),
                        configuredPath=absolute_configured_path,
                        absolutePath=absolute_path,
                        relativePath=os.path.relpath(
                            absolute_path, absolute_configured_path
                        ).replace(os.sep, "/"),
                    )
                )
        elif os.path.isfile(absolute_configured_path):
            scoped.append(
                UnsafeLocalArtifact(
                    syncKey=resolve_artifact_key(absolute_configured_path),
                    configuredPath=absolute_configured_path,
                    absolutePath=absolute_configured_path,
                    relativePath=os.path.basename(absolute_configured_path),
                )
            )
        artifacts.extend(scoped)
    # Dedupe by syncKey (last write wins).
    deduped: dict[str, UnsafeLocalArtifact] = {}
    for artifact in artifacts:
        deduped[artifact.syncKey] = artifact
    return UnsafeLocalArtifactCollection(
        artifacts=list(deduped.values()),
        unavailableConfiguredPaths=unavailable,
    )


def _resolve_unsafe_local_page_path(*, configured_path: str, absolute_path: str) -> dict[str, str]:
    """Compute the ``pageId`` + ``pagePath``
    for an unsafe-local artifact.

    Mirrors the OpenClaw
    ``resolveUnsafeLocalPagePath`` helper.
    """
    configured_base_slug = slugify_wiki_segment(os.path.basename(configured_path))
    configured_hash = hashlib.sha1(os.path.abspath(configured_path).encode("utf-8")).hexdigest()[:8]
    artifact_base_slug = slugify_wiki_segment(os.path.basename(absolute_path))
    artifact_hash = hashlib.sha1(os.path.abspath(absolute_path).encode("utf-8")).hexdigest()[:8]
    page_slug = f"{configured_base_slug}-{configured_hash}" f"-{artifact_base_slug}-{artifact_hash}"
    return {
        "pageId": f"source.unsafe-local.{page_slug}",
        "pagePath": os.path.join(
            "sources", create_wiki_page_filename(f"unsafe-local-{page_slug}")
        ).replace(os.sep, "/"),
    }


def _render_unsafe_local_markdown(artifact: UnsafeLocalArtifact, raw: str, updated_at: str) -> str:
    """Render the unsafe-local source page
    body + frontmatter.

    Mirrors the OpenClaw
    ``writeUnsafeLocalSourcePage`` body
    builder.
    """
    paths = _resolve_unsafe_local_page_path(
        configured_path=artifact.configuredPath,
        absolute_path=artifact.absolutePath,
    )
    title = f"Unsafe Local Import: {artifact.relativePath}"
    body_lines = [
        f"# {title}",
        "",
        "## Unsafe Local Source",
        f"- Configured path: `{artifact.configuredPath}`",
        f"- Relative path: `{artifact.relativePath}`",
        f"- Updated: {updated_at}",
        "",
        "## Content",
        f"```{detect_fence_language(artifact.absolutePath)}",
        raw,
        "```",
        "",
        "## Notes",
        "<!-- openclaw:human:start -->",
        "<!-- openclaw:human:end -->",
        "",
    ]
    return render_wiki_markdown(
        frontmatter={
            "pageType": "source",
            "id": paths["pageId"],
            "title": title,
            "sourceType": "memory-unsafe-local",
            "provenanceMode": "unsafe-local",
            "sourcePath": artifact.absolutePath,
            "unsafeLocalConfiguredPath": artifact.configuredPath,
            "unsafeLocalRelativePath": artifact.relativePath,
            "status": "active",
            "updatedAt": updated_at,
        },
        body="\n".join(body_lines),
    )


async def sync_unsafe_local_sources(
    config: ResolvedMemoryWikiConfig,
) -> BridgeMemoryWikiResult:
    """Sync the unsafe-local sources for ``config``.

    Mirrors the OpenClaw
    :func:`syncMemoryWikiUnsafeLocalSources`.
    Returns a no-op result when the
    vaultMode / allowPrivateMemoryCoreAccess
    flags don't permit the import.
    """
    initialize_memory_wiki_vault(config)
    if (
        config.vaultMode != "unsafe-local"
        or not config.unsafeLocal.allowPrivateMemoryCoreAccess
        or len(config.unsafeLocal.paths) == 0
    ):
        return BridgeMemoryWikiResult(
            imported_count=0,
            updated_count=0,
            skipped_count=0,
            removed_count=0,
            artifact_count=0,
            workspaces=0,
            page_paths=[],
        )

    collection = collect_unsafe_local_artifacts(config.unsafeLocal.paths)
    state = read_memory_wiki_source_sync_state(config.vault.path)
    active_keys: set[str] = set()
    # Preserve sync keys whose configured
    # scope is no longer readable so the
    # human notes survive a temporary
    # mount outage.
    for sync_key, entry in state.entries.items():
        if entry.group != "unsafe-local":
            continue
        if any(
            is_source_within_configured_path(entry.source_path, configured)
            for configured in collection.unavailableConfiguredPaths
        ):
            active_keys.add(sync_key)
    incoming = {a.syncKey for a in collection.artifacts} | active_keys
    assert_memory_wiki_source_sync_state_capacity(
        state=state,
        group="unsafe-local",
        incoming_count=len(incoming),
    )
    # Process the artifacts sequentially
    # (the OpenClaw port uses p-map with
    # concurrency 16; the Python port is
    # sync-IO so a single-threaded loop is
    # the correct Python equivalent).
    results: list[Any] = []
    for artifact in collection.artifacts:
        stats = os.stat(artifact.absolutePath)
        active_keys.add(artifact.syncKey)
        paths = _resolve_unsafe_local_page_path(
            configured_path=artifact.configuredPath,
            absolute_path=artifact.absolutePath,
        )
        render_fingerprint = hashlib.sha1(
            (
                f'{{"configuredPath":"{artifact.configuredPath}",'
                f'"relativePath":"{artifact.relativePath}"}}'
            ).encode()
        ).hexdigest()
        # Read the source content so we
        # can render the body. The Python
        # ``write_imported_source_page``
        # helper takes ``sourceContent`` so
        # we pre-read here.
        with open(artifact.absolutePath, encoding="utf-8") as f:
            raw_source = f.read()
        updated_at = _iso_for_epoch(int(stats.st_mtime * 1000))
        rendered = _render_unsafe_local_markdown(artifact, raw_source, updated_at)
        result = await write_imported_source_page(
            vault_root=config.vault.path,
            sync_key=artifact.syncKey,
            source_path=artifact.absolutePath,
            source_content=raw_source,
            source_updated_at_ms=int(stats.st_mtime * 1000),
            source_size=stats.st_size,
            render_fingerprint=render_fingerprint,
            page_path=paths["pagePath"],
            group="unsafe-local",
            state=state,
            build_rendered=lambda _raw, _updated, _a=artifact, _r=rendered: _r,
        )
        results.append(result)
    removed_count = prune_imported_source_entries(
        vault_root=config.vault.path,
        group="unsafe-local",
        active_keys=active_keys,
        state=state,
    )
    write_memory_wiki_source_sync_state(config.vault.path, state)
    imported_count = sum(1 for r in results if r.changed and r.created)
    updated_count = sum(1 for r in results if r.changed and not r.created)
    skipped_count = sum(1 for r in results if not r.changed)
    page_paths = sorted(r.pagePath for r in results)

    if imported_count > 0 or updated_count > 0 or removed_count > 0:
        append_memory_wiki_log(
            config.vault.path,
            {
                "type": "ingest",
                "details": {
                    "sourceType": "memory-unsafe-local",
                    "configuredPathCount": len(config.unsafeLocal.paths),
                    "artifactCount": len(collection.artifacts),
                    "importedCount": imported_count,
                    "updatedCount": updated_count,
                    "skippedCount": skipped_count,
                    "removedCount": removed_count,
                },
            },
        )
    return BridgeMemoryWikiResult(
        imported_count=imported_count,
        updated_count=updated_count,
        skipped_count=skipped_count,
        removed_count=removed_count,
        artifact_count=len(collection.artifacts),
        workspaces=0,
        page_paths=page_paths,
    )


def _iso_for_epoch(epoch_ms: int) -> str:
    """Format ``epoch_ms`` as an ISO-8601 string."""
    from datetime import datetime

    return datetime.fromtimestamp(epoch_ms / 1000.0, tz=UTC).isoformat().replace("+00:00", "Z")


def reset_memory_wiki_unsafe_local_state_for_tests() -> None:
    """Reset module-level state (test-only helper)."""
    return


__all__ = [
    "DIRECTORY_TEXT_EXTENSIONS",
    "UNSAFE_LOCAL_SYNC_CONCURRENCY",
    "UnsafeLocalArtifact",
    "UnsafeLocalArtifactCollection",
    "collect_unsafe_local_artifacts",
    "detect_fence_language",
    "reset_memory_wiki_unsafe_local_state_for_tests",
    "sync_unsafe_local_sources",
]
