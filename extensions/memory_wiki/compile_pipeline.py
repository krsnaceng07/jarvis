"""compile_pipeline — the memory-wiki compile orchestrator.

OpenClaw parity: mirrors the high-level
``compileMemoryWiki`` entry point from
``extensions/memory-wiki/src/compile.ts``.

Phase 4.3d-mr4 ships the scan-side orchestrator:
``compile_wiki_vault(config)`` walks every ``.md``
file under ``config.vault.path`` (excluding
``.openclaw-wiki/`` + the auto-generated
``index.md`` files), calls
``scan_wiki_page_summary_from_file`` for each, and
returns a :class:`CompileWikiVaultResult` with the
per-page results + a count summary.

The write side (dashboard rendering + per-page
refresh + cache publication) lands in 4.3d-mr5
(compile_render + compile_pages) + 4.3e
(compiled-cache). 4.3d-mr4 deliberately stops at
the scan so the test surface stays small enough
to be reviewable in a single PR.

Surface
-------
- ``COMPILE_PAGE_DIRECTORIES`` -- the 5
  ``{entities, concepts, syntheses, sources,
  reports}/`` subdirectories the scanner walks.
  Matches the OpenClaw ``COMPILE_PAGE_GROUPS``
  shape (sans the per-group ``heading`` field
  which lives in the render layer).
- ``CompileWikiVaultResult`` -- the dataclass
  returned by :func:`compile_wiki_vault`.
- ``compile_wiki_vault(config)`` -- the
  orchestrator.
- ``should_skip_page_for_compile(path)`` -- the
  small helper that decides whether a vault
  ``.md`` file belongs to the compile set.

Concurrency note: OpenClaw's
``READ_PAGE_SUMMARIES_CONCURRENCY = 16`` uses
``runTasksWithConcurrency`` for parallel file
reads. The Python port uses a plain ``for`` loop
for 4.3d-mr4 because (a) the scan is mostly
synchronous and (b) the async concurrency layer
lives in the SDK and the host runtime. 4.3d-mr5
swaps in ``asyncio.gather`` with a semaphore if
the operator opts in via the host config.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .log import (
    COMPILED_SOURCE_DIRECTORIES,
    append_memory_wiki_log,
)
from .time import resolve_memory_wiki_timestamp
from .wiki_page_summary import (
    WikiPageFrontmatterError,
    WikiPageSummary,
    scan_wiki_page_summary_from_file,
)

if TYPE_CHECKING:
    from .config import ResolvedMemoryWikiConfig

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

# The 5 page-group directories. Matches the OpenClaw
# ``COMPILE_PAGE_GROUPS`` shape; the per-group
# ``heading`` field lives in the render layer
# (4.3d-mr5) so this list stays minimal.
COMPILE_PAGE_DIRECTORIES: tuple[str, ...] = COMPILED_SOURCE_DIRECTORIES

# Reserved page stems that the compile pipeline
# skips (auto-generated index files). Mirrors
# OpenClaw's ``WIKI_RESERVED_PAGE_STEMS`` usage in
# the compile layer.
RESERVED_COMPILE_SKIP_STEMS: frozenset[str] = frozenset({"index"})

# Directories the compile pipeline skips entirely
# (vault metadata + dot-dirs). The OpenClaw
# implementation also walks the index pages; the
# Python port skips them at the orchestrator level
# since they have no frontmatter and produce no
# useful WikiPageSummary.
COMPILE_SKIP_DIRECTORIES: frozenset[str] = frozenset(
    {
        ".openclaw-wiki",  # vault metadata
        "_attachments",  # binary attachments
        "_views",  # generated dashboard views
    }
)


@dataclass
class CompileWikiVaultResult:
    """The result of :func:`compile_wiki_vault`.

    Mirrors the OpenClaw compile result shape
    (slimmed for 4.3d-mr4; the full result with
    per-page claim / person-card / link-graph
    breakdowns lands in 4.3d-mr5 + 4.3f).
    """

    vault_path: str
    pages: list[WikiPageSummary] = field(default_factory=list)
    ignored_paths: list[str] = field(default_factory=list)
    invalid_paths: list[WikiPageFrontmatterError] = field(default_factory=list)
    # Diagnostic counts mirror the OpenClaw
    # ``compileMemoryWiki`` return shape.
    scanned_count: int = 0
    invalid_count: int = 0
    ignored_count: int = 0

    @property
    def valid_count(self) -> int:
        """Return the number of valid pages scanned."""
        return len(self.pages)


def should_skip_page_for_compile(relative_path: str) -> bool:
    """Return True iff ``relative_path`` is auto-generated / out-of-scope.

    Mirrors OpenClaw's compile-time page filter:
    skip files under ``.openclaw-wiki/`` /
    ``_attachments/`` / ``_views/``; skip the
    auto-generated ``index.md`` files in each
    vault directory.
    """
    if not relative_path:
        return True
    parts = relative_path.replace(os.sep, "/").split("/")
    if parts[0] in COMPILE_SKIP_DIRECTORIES:
        return True
    if len(parts) > 1 and parts[-1] == "index.md":
        return True
    return len(parts) == 1 and parts[0] in RESERVED_COMPILE_SKIP_STEMS


def _walk_vault_markdown(vault_root: str) -> list[tuple[str, str]]:
    """Return ``[(absolute_path, relative_path), ...]`` for every ``.md`` file.

    The scanner iterates every ``.md`` file under
    ``vault_root`` (recursive) and skips the
    compile-excluded directories + ``index.md``
    files. The relative path uses forward slashes
    so the link graph stays portable.
    """
    abs_root = os.path.abspath(vault_root)
    if not os.path.isdir(abs_root):
        return []
    out: list[tuple[str, str]] = []
    for current_root, dirs, files in os.walk(abs_root):
        # Filter out skip directories in-place
        # so ``os.walk`` doesn't descend into
        # them.
        dirs[:] = [d for d in dirs if d not in COMPILE_SKIP_DIRECTORIES]
        for name in files:
            if not name.endswith(".md"):
                continue
            absolute = os.path.join(current_root, name)
            relative = os.path.relpath(absolute, abs_root).replace(os.sep, "/")
            if should_skip_page_for_compile(relative):
                continue
            out.append((absolute, relative))
    # Stable order: by relative path.
    out.sort(key=lambda pair: pair[1])
    return out


def compile_wiki_vault(
    config: ResolvedMemoryWikiConfig,
    *,
    now_ms: int | None = None,
) -> CompileWikiVaultResult:
    """Walk the vault and scan every ``.md`` page.

    Mirrors the OpenClaw
    ``compileMemoryWiki(config)`` orchestrator
    (scan phase only; the write / cache phase
    lands in 4.3d-mr5). Returns a
    :class:`CompileWikiVaultResult` with the
    per-page ``WikiPageSummary`` + a list of
    ignored paths + a list of invalid-frontmatter
    errors.
    """
    vault_path = config.vault.path
    result = CompileWikiVaultResult(vault_path=vault_path)
    for absolute, relative in _walk_vault_markdown(vault_path):
        scan = scan_wiki_page_summary_from_file(
            absolute_path=absolute,
            vault_root=vault_path,
        )
        status = scan.get("status")
        if status == "valid":
            result.pages.append(scan["page"])
        elif status == "invalid-frontmatter":
            error = scan.get("error")
            if isinstance(error, WikiPageFrontmatterError):
                result.invalid_paths.append(error)
        elif status == "ignored":
            result.ignored_paths.append(relative)
        else:
            # Unknown status → treat as ignored
            # for safety.
            result.ignored_paths.append(relative)
    result.scanned_count = len(result.pages)
    result.invalid_count = len(result.invalid_paths)
    result.ignored_count = len(result.ignored_paths)

    # Append a single ``compile`` log entry so
    # operators can see when the scan ran. The
    # OpenClaw source writes a richer log entry
    # after the cache publication; 4.3d-mr4 just
    # stamps the scan.
    if result.scanned_count or result.invalid_count:
        import contextlib

        with contextlib.suppress(OSError):
            # If the log can't be appended (e.g.
            # read-only vault), don't fail the
            # compile.
            append_memory_wiki_log(
                vault_path,
                {
                    "type": "compile",
                    "timestamp": resolve_memory_wiki_timestamp(now_ms),
                    "details": {
                        "scannedCount": result.scanned_count,
                        "invalidCount": result.invalid_count,
                        "ignoredCount": result.ignored_count,
                    },
                },
            )
    return result


__all__ = [
    "COMPILE_PAGE_DIRECTORIES",
    "COMPILE_SKIP_DIRECTORIES",
    "CompileWikiVaultResult",
    "RESERVED_COMPILE_SKIP_STEMS",
    "compile_wiki_vault",
    "should_skip_page_for_compile",
]
