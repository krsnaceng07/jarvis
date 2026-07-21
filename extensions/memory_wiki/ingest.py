"""ingest — Memory Wiki local-file ingestion (Phase 4.3g-mr2).

OpenClaw parity: mirrors
``extensions/memory-wiki/src/ingest.ts``.

Imports a local text file into the
wiki vault as a ``source`` page,
serialized through the vault mutation
lock so concurrent ingests / compiles /
applies can't tear each other apart.
"""

# ruff: noqa: N815, ASYNC230 — field names mirror the
# OpenClaw camelCase JSON shape so the
# ``wiki.ingest`` gateway response is
# byte-compatible with the OpenClaw host;
# the file reads are bounded (small
# markdown files) and run inside an
# already-serialized vault-mutation
# critical section, so a brief blocking
# I/O is acceptable.

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .compile_pipeline import compile_wiki_vault
from .log import append_memory_wiki_log
from .markdown_pages import (
    render_wiki_markdown,
    slugify_wiki_page_stem,
    slugify_wiki_segment,
)
from .mutation_coordinator import with_memory_wiki_vault_mutation
from .time import resolve_memory_wiki_timestamp
from .vault import initialize_memory_wiki_vault

if TYPE_CHECKING:
    from .config import ResolvedMemoryWikiConfig


@dataclass(frozen=True, slots=True)
class IngestMemoryWikiSourceResult:
    """The result of :func:`ingest_memory_wiki_source`.

    Mirrors the OpenClaw
    ``IngestMemoryWikiSourceResult`` type.
    Field names are camelCase to match the
    ``wiki.ingest`` gateway response
    shape.
    """

    sourcePath: str
    pageId: str
    pagePath: str
    title: str
    bytes: int
    created: bool
    indexUpdatedFiles: list[str]


def _resolve_source_title(source_path: str, explicit_title: str | None) -> str:
    """Return the page title (explicit override
    or the file stem).

    Mirrors the OpenClaw
    ``resolveSourceTitle`` helper.
    """
    if explicit_title and explicit_title.strip():
        return explicit_title.strip()
    base = os.path.basename(source_path)
    stem, _ = os.path.splitext(base)
    return "-_".join(stem.split()).replace("-_", " ").strip() or stem


def _assert_utf8_text(buffer: bytes, source_path: str) -> str:
    """Decode ``buffer`` as UTF-8; reject NUL bytes.

    Mirrors the OpenClaw
    ``assertUtf8Text`` helper.
    """
    preview = buffer[: min(len(buffer), 4096)]
    if b"\x00" in preview:
        raise ValueError(f"Cannot ingest binary file as markdown source: {source_path}")
    return buffer.decode("utf-8")


def _is_empty_existing_source_page(error: object) -> bool:
    """Return True iff ``error`` indicates the
    page doesn't exist on disk yet.

    Mirrors the OpenClaw
    ``isEmptyExistingSourcePage`` helper.
    """
    if not isinstance(error, OSError):
        return False
    errno = getattr(error, "errno", None)
    return errno in (2, 21)  # ENOENT=2, EISDIR=21


async def _read_existing_source_page(page_path: str) -> str:
    """Read the existing source page, returning
    ``""`` if it doesn't exist.

    Mirrors the OpenClaw
    ``readExistingSourcePage`` helper
    (with a single-attempt read; the retry
    is OS-agnostic in Python).
    """
    try:
        with open(page_path, encoding="utf-8") as f:
            return f.read()
    except OSError as exc:
        if _is_empty_existing_source_page(exc):
            return ""
        raise


def _render_markdown_fence(content: str, language: str) -> str:
    """Wrap ``content`` in a triple-backtick
    fence.

    Mirrors the OpenClaw
    ``renderMarkdownFence`` helper.
    """
    return f"```{language}\n{content}\n```"


def _preserve_human_notes_block(rendered: str, existing: str) -> str:
    """Replace the ``<!-- openclaw:human:start
    --> ... <!-- openclaw:human:end -->``
    block in ``rendered`` with the block
    from ``existing`` (preserving human
    notes across re-ingests).

    Mirrors the OpenClaw
    ``preserveHumanNotesBlock`` helper
    via the Python port's existing
    ``replace_managed_markdown_block``
    helper in :mod:`extensions.memory_wiki.markdown`.
    """
    from .markdown import ReplaceManagedBlockParams, replace_managed_markdown_block

    return replace_managed_markdown_block(
        ReplaceManagedBlockParams(
            original=rendered,
            heading="## Notes",
            start_marker="<!-- openclaw:human:start -->",
            end_marker="<!-- openclaw:human:end -->",
            body=_extract_human_notes_block(existing),
        )
    )


def _extract_human_notes_block(existing: str) -> str:
    """Extract the ``## Notes`` content between
    the human-notes start / end markers.
    Returns the inner content (preserves
    the markers).
    """
    start = "<!-- openclaw:human:start -->"
    end = "<!-- openclaw:human:end -->"
    s = existing.find(start)
    if s < 0:
        return ""
    e = existing.find(end, s + len(start))
    if e < 0:
        return ""
    return existing[s : e + len(end)]


async def _ingest_memory_wiki_source_unlocked(
    *,
    config: ResolvedMemoryWikiConfig,
    input_path: str,
    title: str | None,
    now_ms: int | None,
) -> IngestMemoryWikiSourceResult:
    """The unlocked ingest body.

    Mirrors the OpenClaw
    ``ingestMemoryWikiSourceUnlocked``
    function.
    """
    initialize_memory_wiki_vault(config, now_ms=now_ms)
    source_path = os.path.abspath(input_path)
    with open(source_path, "rb") as f:
        buffer = f.read()
    content = _assert_utf8_text(buffer, source_path)
    page_title = _resolve_source_title(source_path, title)
    slug = slugify_wiki_segment(page_title)
    page_stem = slugify_wiki_page_stem(page_title)
    page_id = f"source.{slug}"
    page_relative_path = f"sources/{page_stem}.md"
    page_path = os.path.join(config.vault.path, page_relative_path)
    created = not os.path.isfile(page_path)
    timestamp = resolve_memory_wiki_timestamp(now_ms)

    body_lines = [
        f"# {page_title}",
        "",
        "## Source",
        "- Type: `local-file`",
        f"- Path: `{source_path}`",
        f"- Bytes: {len(buffer)}",
        f"- Updated: {timestamp}",
        "",
        "## Content",
        _render_markdown_fence(content, "text"),
        "",
        "## Notes",
        "<!-- openclaw:human:start -->",
        "<!-- openclaw:human:end -->",
        "",
    ]
    markdown = render_wiki_markdown(
        frontmatter={
            "pageType": "source",
            "id": page_id,
            "title": page_title,
            "sourceType": "local-file",
            "sourcePath": source_path,
            "ingestedAt": timestamp,
            "updatedAt": timestamp,
            "status": "active",
        },
        body="\n".join(body_lines),
    )

    if not created:
        existing = await _read_existing_source_page(page_path)
        if existing:
            markdown = _preserve_human_notes_block(markdown, existing)
    with open(page_path, "w", encoding="utf-8") as f:
        f.write(markdown)

    append_memory_wiki_log(
        config.vault.path,
        {
            "type": "ingest",
            "details": {
                "inputPath": source_path,
                "pageId": page_id,
                "pagePath": page_relative_path,
                "bytes": len(buffer),
                "created": created,
            },
        },
    )
    compile_result = compile_wiki_vault(config)
    return IngestMemoryWikiSourceResult(
        sourcePath=source_path,
        pageId=page_id,
        pagePath=page_relative_path,
        title=page_title,
        bytes=len(buffer),
        created=created,
        indexUpdatedFiles=compile_result.updated_files,
    )


async def ingest_memory_wiki_source(
    *,
    config: ResolvedMemoryWikiConfig,
    input_path: str,
    title: str | None = None,
    now_ms: int | None = None,
) -> IngestMemoryWikiSourceResult:
    """Ingest a local text file into the wiki
    vault as a ``source`` page.

    Mirrors the OpenClaw
    :func:`ingestMemoryWikiSource`. The
    body runs under the vault mutation
    lock so it can't interleave with
    apply / compile / source-sync.
    """
    return await with_memory_wiki_vault_mutation(
        config.vault.path,
        lambda: _ingest_memory_wiki_source_unlocked(
            config=config,
            input_path=input_path,
            title=title,
            now_ms=now_ms,
        ),
    )


def reset_memory_wiki_ingest_state_for_tests() -> None:
    """Reset module-level state (test-only helper)."""
    return


__all__ = [
    "IngestMemoryWikiSourceResult",
    "ingest_memory_wiki_source",
    "reset_memory_wiki_ingest_state_for_tests",
]
