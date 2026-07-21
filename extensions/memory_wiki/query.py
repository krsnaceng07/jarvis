"""query — Memory Wiki query helpers (read path + lookup).

OpenClaw parity: mirrors
``extensions/memory-wiki/src/query.ts``.

Phase 4.3f-mr1 ships the read path: every
vault ``.md`` file under
``entities/`` / ``concepts/`` / ``sources/`` /
``syntheses/`` / ``reports/`` is scanned,
parsed into a :class:`WikiPageSummary`, and
returned with the raw markdown body so a
caller can do line-range slicing.

The full search + memory-corpus fallback
(``searchMemoryWiki``) lands in 4.3f-mr2.
"""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from .compile_pipeline import COMPILE_PAGE_DIRECTORIES
from .markdown import parse_wiki_frontmatter
from .wiki_page_summary import (
    WikiPageSummary,
    scan_wiki_page_summary,
)

if TYPE_CHECKING:
    from .config import ResolvedMemoryWikiConfig


# Mirrors the OpenClaw
# ``QUERY_PAGE_READ_CONCURRENCY = 16``
# constant.
QUERY_PAGE_READ_CONCURRENCY = 16

# Mirrors the OpenClaw ``QUERY_DIRS`` constant.
QUERY_DIRS: tuple[str, ...] = COMPILE_PAGE_DIRECTORIES

# Mirrors the OpenClaw ``WIKI_SEARCH_MODES``
# constant. The full search implementation
# lives in 4.3f-mr2; the constant is
# re-exported so callers can type their
# search params.
WIKI_SEARCH_MODES: tuple[str, ...] = (
    "auto",
    "find-person",
    "route-question",
    "source-evidence",
    "raw-claim",
)
WikiSearchMode = Literal["auto", "find-person", "route-question", "source-evidence", "raw-claim"]


@dataclass(frozen=True, slots=True)
class QueryableWikiPage:
    """A wiki page with its raw markdown body.

    Mirrors the OpenClaw
    ``QueryableWikiPage = WikiPageSummary & {raw: string}``.
    """

    page: WikiPageSummary
    raw: str


@dataclass(frozen=True, slots=True)
class WikiGetResult:
    """The ``getMemoryWikiPage`` return shape. Mirrors the OpenClaw ``WikiGetResult``."""

    corpus: str  # "wiki" | "memory"
    path: str
    title: str
    kind: str
    content: str
    from_line: int
    line_count: int
    total_lines: int | None = None
    truncated: bool | None = None
    id: str | None = None
    source_type: str | None = None
    provenance_mode: str | None = None
    source_path: str | None = None
    provenance_label: str | None = None
    updated_at: str | None = None


# ── helpers ────────────────────────────────────────────────


def _normalize_lookup_key(value: str) -> str:
    """Normalize a lookup string.

    Mirrors the OpenClaw
    ``normalizeLookupKey``:
    - trim whitespace
    - replace backslashes with forward slashes
    - if the value ends with ``.md``, keep it
      as-is; otherwise strip trailing slashes
    """
    normalized = value.strip().replace("\\", "/")
    if normalized.endswith(".md"):
        return normalized
    return normalized.rstrip("/")


def build_lookup_candidates(lookup: str) -> list[str]:
    """Build the set of lookup candidates.

    Mirrors the OpenClaw
    ``buildLookupCandidates``: returns the
    normalized key + the same key with ``.md``
    appended (when not already present). The
    order is preserved for stable resolution.
    """
    normalized = _normalize_lookup_key(lookup)
    with_extension = normalized if normalized.endswith(".md") else f"{normalized}.md"
    seen: set[str] = set()
    out: list[str] = []
    for candidate in (normalized, with_extension):
        if candidate not in seen:
            seen.add(candidate)
            out.append(candidate)
    return out


def should_search_wiki(config: ResolvedMemoryWikiConfig) -> bool:
    """Return True iff the wiki corpus is enabled for ``config``.

    Mirrors the OpenClaw
    ``shouldSearchWiki``: the wiki corpus is
    searched when ``config.search.corpus`` is
    ``"wiki"`` or ``"all"``.
    """
    corpus = getattr(config.search, "corpus", "wiki")
    return corpus in ("wiki", "all")


# ── read path ─────────────────────────────────────────────


def list_wiki_markdown_files(root_dir: str) -> list[str]:
    """Return every ``.md`` file under the per-kind subdirectories.

    Mirrors the OpenClaw
    ``listWikiMarkdownFiles``. Skips the
    auto-generated ``index.md`` files (the
    compile pipeline's index writers create
    them per-kind). Returns an
    alphabetically-sorted list of forward-slash
    relative paths.
    """
    if not os.path.isdir(root_dir):
        return []
    out: list[str] = []
    for relative_dir in QUERY_DIRS:
        dir_path = os.path.join(root_dir, relative_dir)
        if not os.path.isdir(dir_path):
            continue
        for current_root, _dirs, files in os.walk(dir_path):
            for name in files:
                if not name.endswith(".md"):
                    continue
                if name == "index.md":
                    continue
                absolute = os.path.join(current_root, name)
                relative = os.path.relpath(absolute, root_dir).replace(os.sep, "/")
                out.append(relative)
    out.sort()
    return out


def _read_one_page(root_dir: str, relative_path: str) -> QueryableWikiPage | None:
    """Read + scan a single page. Returns ``None`` for un-parseable files."""
    absolute = os.path.join(root_dir, relative_path)
    try:
        with open(absolute, encoding="utf-8") as f:
            raw = f.read()
    except OSError:
        return None
    scan = scan_wiki_page_summary(
        absolute_path=absolute, relative_path=relative_path, raw_markdown=raw
    )
    if scan.get("status") != "valid":
        return None
    page: WikiPageSummary = scan["page"]  # type: ignore[assignment]
    return QueryableWikiPage(page=page, raw=raw)


def _read_one_page_at(root_dir: str, relative_path: str) -> QueryableWikiPage | None:
    """Module-level wrapper around :func:`_read_one_page` for thread-pool pickling.

    The default ``ThreadPoolExecutor`` pickles
    the callables it ships to workers, so the
    inner helper must be reachable at module
    level (no closure over ``root_dir``).
    """
    return _read_one_page(root_dir, relative_path)


def read_queryable_wiki_pages(root_dir: str) -> list[QueryableWikiPage]:
    """Read every queryable wiki page under ``root_dir``.

    Mirrors the OpenClaw
    ``readQueryableWikiPages``. Reads files
    concurrently via a thread pool (capped at
    :data:`QUERY_PAGE_READ_CONCURRENCY`).
    Un-parseable files are silently skipped
    (mirroring the OpenClaw ``pMapSkip``
    behavior).
    """
    files = list_wiki_markdown_files(root_dir)
    if not files:
        return []
    out: list[QueryableWikiPage] = []
    with ThreadPoolExecutor(
        max_workers=min(QUERY_PAGE_READ_CONCURRENCY, len(files)),
    ) as pool:
        # Bind ``root_dir`` via a partial so the
        # pool's worker can pickle the callable.
        from functools import partial

        worker = partial(_read_one_page_at, root_dir)
        for page in pool.map(worker, files):
            if page is not None:
                out.append(page)
    return out


def read_queryable_wiki_pages_by_paths(
    root_dir: str,
    files: list[str],
) -> list[QueryableWikiPage]:
    """Read the wiki pages whose relative paths are in ``files``.

    Mirrors the OpenClaw
    ``readQueryableWikiPagesByPaths``. Files
    that don't exist on disk or fail to parse
    are silently dropped.
    """
    if not files:
        return []
    out: list[QueryableWikiPage] = []
    for relative_path in files:
        page = _read_one_page(root_dir, relative_path)
        if page is not None:
            out.append(page)
    return out


def resolve_queryable_wiki_page_by_lookup(
    pages: list[QueryableWikiPage],
    lookup: str,
) -> QueryableWikiPage | None:
    """Resolve a single page from ``pages`` by ``lookup`` string.

    Mirrors the OpenClaw
    ``resolveQueryableWikiPageByLookup``.
    Tries (in order):
    1. Exact ``relativePath`` match.
    2. Exact ``relativePath`` match with
       ``.md`` appended.
    3. ``relativePath`` without ``.md``
       extension match.
    4. Basename (without ``.md``) match.
    5. ``id`` match.
    """
    key = _normalize_lookup_key(lookup)
    with_extension = key if key.endswith(".md") else f"{key}.md"
    without_extension = key[:-3] if key.endswith(".md") else key
    basename = without_extension.rsplit("/", 1)[-1]
    for page in pages:
        if page.page.relative_path == key:
            return page
    for page in pages:
        if page.page.relative_path == with_extension:
            return page
    for page in pages:
        path_no_ext = page.page.relative_path
        if path_no_ext.endswith(".md") and path_no_ext[:-3] == key:
            return page
    for page in pages:
        rel = page.page.relative_path
        if rel.endswith(".md") and rel.rsplit("/", 1)[-1][:-3] == basename:
            return page
    for page in pages:
        if page.page.id == key:
            return page
    return None


# ── public get ────────────────────────────────────────────


def _parse_body_lines(raw: str) -> list[str]:
    """Return the body lines (post-frontmatter) split on newlines.

    Mirrors the OpenClaw
    ``parseWikiMarkdown(page.raw).body.split(/\r?\n/)``.
    """
    parsed = parse_wiki_frontmatter(raw)
    if parsed is None:
        # Fall back to the raw text (no
        # frontmatter). The OpenClaw
        # ``parseWikiMarkdown`` would also
        # tolerate missing frontmatter; the
        # Python port uses
        # ``parse_wiki_frontmatter`` (which
        # returns ``None`` when the
        # frontmatter is missing or corrupt).
        return raw.splitlines()
    body = parsed.body
    if not isinstance(body, str):
        return []
    return body.splitlines()


def get_memory_wiki_page(
    *,
    config: ResolvedMemoryWikiConfig,
    lookup: str,
    from_line: int | None = None,
    line_count: int | None = None,
) -> WikiGetResult | None:
    """Read a single wiki page (line-range slice).

    Mirrors the OpenClaw ``getMemoryWikiPage``
    (wiki-corpus branch only; the shared-memory
    fallback is added in 4.3f-mr2).

    The page is located by ``lookup`` (see
    :func:`resolve_queryable_wiki_page_by_lookup`).
    The body is sliced between ``from_line``
    (1-indexed, default 1) and
    ``from_line + line_count`` (default 200).
    """
    from .vault import initialize_memory_wiki_vault

    initialize_memory_wiki_vault(config)
    if not should_search_wiki(config):
        return None
    pages = read_queryable_wiki_pages(config.vault.path)
    page = resolve_queryable_wiki_page_by_lookup(pages, lookup)
    if page is None:
        return None
    effective_from = from_line if isinstance(from_line, int) and from_line >= 1 else 1
    effective_count = line_count if isinstance(line_count, int) and line_count >= 1 else 200
    lines = _parse_body_lines(page.raw)
    total = len(lines)
    start_idx = effective_from - 1
    end_idx = min(start_idx + effective_count, total)
    slice_text = "\n".join(lines[start_idx:end_idx])
    truncated = end_idx < total
    return WikiGetResult(
        corpus="wiki",
        path=page.page.relative_path,
        title=page.page.title,
        kind=page.page.kind,
        content=slice_text,
        from_line=effective_from,
        line_count=effective_count,
        total_lines=total,
        truncated=truncated,
        id=page.page.id,
        source_type=page.page.source_type,
        provenance_mode=page.page.provenance_mode,
        source_path=page.page.source_path,
        provenance_label=page.page.bridge_relative_path,
        updated_at=page.page.updated_at,
    )


# ── legacy state alias for OpenClaw parity ────────────────


def reset_memory_wiki_query_state_for_tests() -> None:
    """Reset module-level state (test-only helper).

    The read path is stateless; this helper
    exists so test code can call a known
    name (mirroring the OpenClaw
    ``resetMemoryWikiQueryStateForTests``
    pattern used by other modules).
    """
    return


__all__ = [
    "QUERY_DIRS",
    "QUERY_PAGE_READ_CONCURRENCY",
    "QueryableWikiPage",
    "WIKI_SEARCH_MODES",
    "WikiGetResult",
    "WikiSearchMode",
    "build_lookup_candidates",
    "get_memory_wiki_page",
    "list_wiki_markdown_files",
    "read_queryable_wiki_pages",
    "read_queryable_wiki_pages_by_paths",
    "resolve_queryable_wiki_page_by_lookup",
    "reset_memory_wiki_query_state_for_tests",
    "should_search_wiki",
]
