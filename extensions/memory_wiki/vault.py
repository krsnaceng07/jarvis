"""vault — memory-wiki vault initialization.

OpenClaw parity: mirrors
``extensions/memory-wiki/src/vault.ts``.

The vault initializer scaffolds a fresh
``memory-wiki`` vault on disk:
- Creates the standard directory tree
  (``entities/``, ``concepts/``, ``syntheses/``,
  ``sources/``, ``reports/``, ``_attachments/``,
  ``_views/``, ``.openclaw-wiki/``).
- Writes the scaffold files (``AGENTS.md``,
  ``WIKI.md``, ``index.md``, ``inbox.md``,
  ``.openclaw-wiki/log.jsonl``) when missing.
- Mints a ``vaultGeneration`` UUID if the log is
  empty.
- Invalidates the compiled cache when the scaffold
  was missing (matches OpenClaw's
  ``invalidateMemoryWikiCompiledCache`` call on
  incomplete-scaffold detection).
- Appends a ``vault-generation`` log entry on first
  init so the durable identity is anchored.

The init is idempotent: re-running it on an
already-initialized vault is a no-op (all the
``writeFileIfMissing`` calls short-circuit on the
``already-exists`` guard).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from jarvis_sdk import FsSafeError, fs_root, path_exists

from .log import (
    COMPILED_SOURCE_DIRECTORIES,
    append_memory_wiki_log,
    ensure_memory_wiki_vault_generation,
    load_memory_wiki_validated_vault_identity,
    resolve_memory_wiki_vault_source_generation,
)
from .time import resolve_memory_wiki_timestamp

if TYPE_CHECKING:
    from .config import ResolvedMemoryWikiConfig

# Module-level constants mirror OpenClaw's
# ``WIKI_VAULT_DIRECTORIES`` and ``WIKI_VAULT_SCAFFOLD``
# ``as const`` arrays. The Python port uses a
# ``tuple`` (immutable, sequence-friendly) instead of
# a TypeScript ``readonly array``.
WIKI_VAULT_DIRECTORIES: tuple[str, ...] = (
    "entities",
    "concepts",
    "syntheses",
    "sources",
    "reports",
    "_attachments",
    "_views",
    ".openclaw-wiki",
)

WIKI_VAULT_SCAFFOLD: tuple[str, ...] = (
    "AGENTS.md",
    "WIKI.md",
    "index.md",
    "inbox.md",
    ".openclaw-wiki/log.jsonl",
)


# Maximum size (in bytes) for the
# ``.openclaw-wiki/log.jsonl`` empty-file create.
# The scaffold creates an empty log file so the
# ``appendRegularFile`` call on the first real entry
# doesn't race with a parallel init.
EMPTY_LOG_BYTES = 0


@dataclass
class InitializeMemoryWikiVaultResult:
    """The result of :func:`initialize_memory_wiki_vault`.

    Mirrors OpenClaw's ``InitializeMemoryWikiVaultResult``
    type. ``created`` is True when at least one
    directory or scaffold file was actually created
    (matches the OpenClaw
    ``created: createdDirectories.length > 0 || createdFiles.length > 0``
    predicate).
    """

    root_dir: str
    created: bool
    created_directories: list[str] = field(default_factory=list)
    created_files: list[str] = field(default_factory=list)


def _build_index_markdown() -> str:
    """Return the scaffold ``index.md`` body.

    Mirrors OpenClaw's ``buildIndexMarkdown``. The
    ``## Generated`` block is left as a managed
    markdown block so the compile pipeline can
    replace it later.
    """
    return _build_managed_block(
        original="# Wiki Index\n",
        heading="## Generated",
        start_marker="<!-- openclaw:wiki:index:start -->",
        end_marker="<!-- openclaw:wiki:index:end -->",
        body="- No compiled pages yet.",
    )


def _build_agents_markdown() -> str:
    """Return the scaffold ``AGENTS.md`` body.

    Mirrors OpenClaw's ``buildAgentsMarkdown``. Lists
    the maintainer rules (managed blocks, human
    notes, source-backed claims, structured
    ``claims`` frontmatter, machine-read tools).
    """
    return _with_trailing_newline(
        """# Memory Wiki Agent Guide

- Treat generated blocks as plugin-owned.
- Preserve human notes outside managed markers.
- Prefer source-backed claims over wiki-to-wiki citation loops.
- Prefer structured `claims` with evidence over burying key beliefs only in prose.
- Use the wiki tools for machine reads; Markdown pages are the human view.
"""
    )


def _build_wiki_overview_markdown(config: ResolvedMemoryWikiConfig) -> str:
    """Return the scaffold ``WIKI.md`` body.

    Mirrors OpenClaw's ``buildWikiOverviewMarkdown``.
    Includes the vault mode, render mode, and search
    corpus default so operators can verify the
    active configuration from a glance at the
    vault root.
    """
    raw_source_marker = "<!-- openclaw:wiki:raw-source -->"
    return _with_trailing_newline(
        f"""# Memory Wiki

This vault is maintained by the JARVIS memory-wiki plugin.

- Vault mode: `{config.vaultMode}`
- Render mode: `{config.vault.renderMode}`
- Search corpus default: `{config.search.corpus}`

## Architecture
- Raw sources remain the evidence layer.
- To keep unmanaged raw Markdown in `sources/`, add `{raw_source_marker}` near the top of the page.
- Wiki pages are the human-readable synthesis layer.
- Compiled query and prompt snapshots live in JARVIS plugin state, not vault files.

## Notes
<!-- openclaw:human:start -->
<!-- openclaw:human:end -->
"""
    )


def _build_inbox_markdown() -> str:
    """Return the scaffold ``inbox.md`` body.

    Mirrors OpenClaw's inline ``inbox.md`` content.
    """
    return _with_trailing_newline("# Inbox\n\nDrop raw ideas, questions, and source links here.\n")


def _with_trailing_newline(text: str) -> str:
    """Ensure ``text`` ends with exactly one newline.

    Mirrors OpenClaw's ``withTrailingNewline``.
    """
    if not text.endswith("\n"):
        return text + "\n"
    return text


def _build_managed_block(
    *,
    original: str,
    heading: str,
    start_marker: str,
    end_marker: str,
    body: str,
) -> str:
    """Build a scaffold markdown file with one managed block.

    Mirrors OpenClaw's
    ``replaceManagedMarkdownBlock({ original, heading,
    startMarker, endMarker, body })``. The Python
    port inlines the replacement logic (the
    ``markdown_managed_blocks`` module from 4.3c-mr2
    exposes it as a reusable helper).
    """
    if not original.endswith("\n"):
        original = original + "\n"
    block = f"{start_marker}\n{heading}\n\n{body}\n{end_marker}\n"
    return _with_trailing_newline(original + block)


def _write_file_if_missing(
    *,
    vault: object,
    root_dir: str,
    relative_path: str,
    content: str,
    created_files: list[str],
) -> None:
    """Best-effort scaffold write.

    Mirrors OpenClaw's ``writeFileIfMissing``. Tries
    the fs-safe ``vault.create`` (which raises
    ``FsSafeError("already-exists")`` on a duplicate)
    and silently skips when the file already exists.
    Other ``FsSafeError`` codes (symlink, out-of-root)
    are propagated. On success, appends the absolute
    file path to ``created_files`` (matches
    OpenClaw's ``path.join(rootDir, relativePath)``).
    """
    try:
        vault.create(relative_path, content)  # type: ignore[attr-defined]
    except FsSafeError as exc:
        if exc.code == "already-exists":
            return
        raise
    created_files.append(os.path.join(root_dir, relative_path))


def _invalidate_compiled_cache_if_needed(
    *,
    config: ResolvedMemoryWikiConfig,
    root_dir: str,
    had_vault_scaffold: bool,
) -> None:
    """Invalidate the compiled cache when the scaffold was missing.

    Mirrors OpenClaw's
    ``invalidateMemoryWikiCompiledCache(config)``
    call. The Python port stubs the invalidation as
    a no-op (the compiled-cache module lands in
    Phase 4.3e) but recomputes the source-tree hash
    so the validated identity can be re-checked by
    subsequent reads.

    For now, we just record the divergent
    ``resolveMemoryWikiVaultSourceGeneration`` so
    tests can observe the trigger without depending
    on the compiled cache yet.
    """
    if had_vault_scaffold:
        return
    # Touch ``resolveMemoryWikiVaultSourceGeneration``
    # so the side-effect (``InMemoryWikiCompiledCache
    # invalidation`` in the real port) is exercised.
    # Phase 4.3e will wire this to the real
    # ``invalidateMemoryWikiCompiledCache`` call.
    resolve_memory_wiki_vault_source_generation(root_dir)
    # No-op for now: the compiled-cache module
    # (Phase 4.3e) owns the actual invalidation.
    return


def initialize_memory_wiki_vault(
    config: ResolvedMemoryWikiConfig,
    *,
    now_ms: int | None = None,
) -> InitializeMemoryWikiVaultResult:
    """Initialize a memory-wiki vault at ``config.vault.path``.

    Mirrors OpenClaw's ``initializeMemoryWikiVault``.
    Idempotent: re-running on an already-initialized
    vault is a no-op (scaffold files are skipped, no
    ``vault-generation`` entry is duplicated).

    Returns a
    :class:`InitializeMemoryWikiVaultResult` that
    lists the directories and files that were
    actually created (so callers can log a
    human-readable diff).
    """
    root_dir = config.vault.path
    created_directories: list[str] = []
    created_files: list[str] = []
    root_created = not path_exists(root_dir)
    if root_created:
        created_directories.append(root_dir)
    os.makedirs(root_dir, exist_ok=True)

    had_vault_scaffold = all(
        path_exists(os.path.join(root_dir, relative_path)) for relative_path in WIKI_VAULT_SCAFFOLD
    )
    if not had_vault_scaffold:
        # Missing scaffold means a new / recreated
        # vault, even when its parent directory
        # survived. Invalidate the compiled cache.
        _invalidate_compiled_cache_if_needed(
            config=config,
            root_dir=root_dir,
            had_vault_scaffold=False,
        )

    for relative_dir in WIKI_VAULT_DIRECTORIES:
        full_path = os.path.join(root_dir, relative_dir)
        if not path_exists(full_path):
            created_directories.append(full_path)
        os.makedirs(full_path, exist_ok=True)

    vault = fs_root(root_dir)
    _write_file_if_missing(
        vault=vault,
        root_dir=root_dir,
        relative_path="AGENTS.md",
        content=_build_agents_markdown(),
        created_files=created_files,
    )
    _write_file_if_missing(
        vault=vault,
        root_dir=root_dir,
        relative_path="WIKI.md",
        content=_build_wiki_overview_markdown(config),
        created_files=created_files,
    )
    _write_file_if_missing(
        vault=vault,
        root_dir=root_dir,
        relative_path="index.md",
        content=_build_index_markdown(),
        created_files=created_files,
    )
    _write_file_if_missing(
        vault=vault,
        root_dir=root_dir,
        relative_path="inbox.md",
        content=_build_inbox_markdown(),
        created_files=created_files,
    )
    _write_file_if_missing(
        vault=vault,
        root_dir=root_dir,
        relative_path=".openclaw-wiki/log.jsonl",
        content="",
        created_files=created_files,
    )

    if created_directories or created_files:
        # Log the init with a human-readable relative-
        # path diff (matches the OpenClaw
        # ``path.relative(rootDir, dir) || "."`` shape).
        relative_dirs = [os.path.relpath(d, root_dir) or "." for d in created_directories]
        relative_files = [os.path.relpath(f, root_dir) for f in created_files]
        append_memory_wiki_log(
            root_dir,
            {
                "type": "init",
                "timestamp": resolve_memory_wiki_timestamp(now_ms),
                "details": {
                    "createdDirectories": relative_dirs,
                    "createdFiles": relative_files,
                },
            },
        )

    # Ensure the vault generation is durable. This
    # appends a ``vault-generation`` entry on first
    # init and is a no-op on subsequent calls.
    ensure_memory_wiki_vault_generation(root_dir)

    # Validate the identity after init so callers can
    # surface a stale publication if the source tree
    # was restored mid-init. (No-op for fresh vaults
    # since no publication id is recorded yet.)
    load_memory_wiki_validated_vault_identity(root_dir)

    # The compiled cache owner is activated by
    # ``index.py`` (Phase 4.3g) once the lifecycle
    # service lands. Phase 4.3c intentionally does
    # not call
    # ``activateMemoryWikiCompiledCacheOwner`` /
    # ``reconcileMemoryWikiCompiledCacheOwner`` —
    # those touch the cache store which lives in
    # Phase 4.3e.
    return InitializeMemoryWikiVaultResult(
        root_dir=root_dir,
        created=bool(created_directories) or bool(created_files),
        created_directories=created_directories,
        created_files=created_files,
    )


# Re-export the COMPILED_SOURCE_DIRECTORIES for
# callers that need to walk the same source set
# (e.g. the compile pipeline in 4.3d).
__all__ = [
    "COMPILED_SOURCE_DIRECTORIES",
    "EMPTY_LOG_BYTES",
    "InitializeMemoryWikiVaultResult",
    "WIKI_VAULT_DIRECTORIES",
    "WIKI_VAULT_SCAFFOLD",
    "initialize_memory_wiki_vault",
]
