"""compile_pages — the per-page compile loop.

OpenClaw parity: mirrors the
``compileMemoryWikiPages`` /
``buildRelated``
helpers from
``extensions/memory-wiki/src/compile.ts``.

Phase 4.3d-mr6 ships the per-page write loop:
``write_compiled_pages(config, pages)`` iterates
each scanned :class:`WikiPageSummary`, builds
the OpenClaw-shaped related block, and persists
the page via the ``with_memory_wiki_vault_mutation``
+ ``write_guarded_vault_page`` pair.

The full body re-render (which writes
``## Related`` / preserves the human-notes block /
rewrites the frontmatter) is implemented in
``build_page_body`` below. The disk-write step
is implemented in ``write_compiled_pages``.

Surface
-------
- ``build_related_block(related_pages)`` -- build
  the ``## Related`` block content.
- ``build_page_body(page, related_pages)`` -- build
  the full page body (preserving human notes).
- ``write_compiled_pages(config, pages)`` -- the
  per-page write loop. Returns a list of
  ``PageWriteResult``.
- ``PageWriteResult`` -- the per-page write
  outcome.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from jarvis_sdk import lowercase_preserving_whitespace

from .claim_health import _read_attr
from .markdown import (
    WIKI_RELATED_END_MARKER,
    WIKI_RELATED_START_MARKER,
)
from .markdown_pages import render_wiki_markdown
from .mutation_coordinator import with_memory_wiki_vault_mutation
from .vault_page_write import write_guarded_vault_page

if TYPE_CHECKING:
    from .config import ResolvedMemoryWikiConfig
    from .wiki_page_summary import WikiPageSummary

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

# Mirrors the OpenClaw ``MAX_RELATED_PAGES_PER_SECTION``
# constant. The compile-time related block caps
# at 12 entries per kind (sources / backlinks /
# related-pages).
MAX_RELATED_PAGES_PER_SECTION = 12

# Cap on the per-page body line length to keep
# the related block readable.
MAX_RELATED_LINE_LENGTH = 240

# Human-note block markers. The compile pipeline
# preserves whatever the user wrote between
# these markers; the OpenClaw behavior is
# "human wins".
HUMAN_START_MARKER = "<!-- openclaw:human:start -->"
HUMAN_END_MARKER = "<!-- openclaw:human:end -->"


@dataclass
class PageWriteResult:
    """The per-page write outcome.

    Mirrors the OpenClaw ``compileMemoryWikiPages``
    return-row shape (slimmed for 4.3d-mr6).
    """

    absolute_path: str
    relative_path: str
    written: bool
    related_count: int = 0
    error: str | None = None


def build_related_block(
    related_pages: list[tuple[WikiPageSummary, str]],
) -> str:
    """Build the ``## Related`` managed block body.

    Mirrors the OpenClaw
    ``buildManagedRelatedBlock``. Each entry is
    ``(page, label)`` where ``label`` is a short
    description like "source", "backlink", or
    "related".

    The block is wrapped in
    :data:`WIKI_RELATED_START_MARKER` /
    :data:`WIKI_RELATED_END_MARKER` so the
    ``extract_wiki_links`` helper can skip it.
    """
    if not related_pages:
        return (
            f"{WIKI_RELATED_START_MARKER}\n"
            "## Related\n\n"
            "- No related pages yet.\n"
            f"{WIKI_RELATED_END_MARKER}\n"
        )
    lines = [
        WIKI_RELATED_START_MARKER,
        "## Related",
        "",
    ]
    for page, label in related_pages[:MAX_RELATED_PAGES_PER_SECTION]:
        # Truncate the title to keep the line
        # readable; the OpenClaw source uses
        # ``capWikiValueWithHash`` for the same
        # purpose.
        title = _read_attr(page, "title") or ""
        if len(title) > MAX_RELATED_LINE_LENGTH:
            title = title[: MAX_RELATED_LINE_LENGTH - 1] + "\u2026"
        page_rel = _read_attr(page, "relativePath", "relative_path") or ""
        lines.append(f"- {label}: [{title}]({page_rel})")
    if len(related_pages) > MAX_RELATED_PAGES_PER_SECTION:
        lines.append(f"- ... and {len(related_pages) - MAX_RELATED_PAGES_PER_SECTION} more")
    lines.append(WIKI_RELATED_END_MARKER)
    return "\n".join(lines) + "\n"


def _resolve_related_pages(
    page: WikiPageSummary,
    all_pages: list[WikiPageSummary],
) -> list[tuple[WikiPageSummary, str]]:
    """Build the list of related pages for ``page``.

    Mirrors the OpenClaw
    ``buildManagedRelatedBlockLinks`` (the
    sources / backlinks / related split is
    simplified for 4.3d-mr6). A page is "related"
    when ``page`` links to it via the link graph
    OR when some other page links to ``page``.
    """
    page_relative = _read_attr(page, "relativePath", "relative_path") or ""
    page_lower = lowercase_preserving_whitespace(page_relative)
    sources: list[WikiPageSummary] = []
    backlinks: list[WikiPageSummary] = []
    related: list[WikiPageSummary] = []
    seen: set[str] = set()
    seen.add(page_lower)
    for other in all_pages:
        if other is page:
            continue
        other_relative = _read_attr(other, "relativePath", "relative_path") or ""
        other_lower = lowercase_preserving_whitespace(other_relative)
        if other_lower in seen:
            continue
        other_targets = {
            lowercase_preserving_whitespace(target)
            for target in (_read_attr(other, "linkTargets", "link_targets") or [])
        }
        if page_lower in other_targets:
            backlinks.append(other)
            seen.add(other_lower)
            continue
        this_targets = {
            lowercase_preserving_whitespace(target)
            for target in (_read_attr(page, "linkTargets", "link_targets") or [])
        }
        if other_lower in this_targets:
            sources.append(other)
            seen.add(other_lower)
            continue
        # Otherwise the page is "related" if it
        # shares a source id with the current
        # page.
        page_source_ids = set(_read_attr(page, "sourceIds", "source_ids") or [])
        other_source_ids = set(_read_attr(other, "sourceIds", "source_ids") or [])
        if page_source_ids & other_source_ids:
            related.append(other)
            seen.add(other_lower)
    out: list[tuple[WikiPageSummary, str]] = []
    for page_obj in sources:
        out.append((page_obj, "source"))
    for page_obj in backlinks:
        out.append((page_obj, "backlink"))
    for page_obj in related:
        out.append((page_obj, "related"))
    return out


def build_page_body(
    page: WikiPageSummary,
    related_pages: list[tuple[WikiPageSummary, str]],
) -> str:
    """Build the rewritten page body.

    Mirrors the OpenClaw
    ``compileMemoryWikiPages`` body builder. The
    body preserves the user's frontmatter (with
    ``updatedAt`` + ``lastRefreshedAt`` stamps) and
    adds / refreshes the ``## Related`` managed
    block. The human-notes block is preserved
    verbatim (the OpenClaw source keeps the
    user's text inside the
    ``<!-- openclaw:human:start/end -->`` markers).
    """
    title = _read_attr(page, "title") or ""
    kind = _read_attr(page, "kind") or "entity"
    page_id = _read_attr(page, "id")
    aliases = _read_attr(page, "aliases") or []
    source_ids = _read_attr(page, "sourceIds", "source_ids") or []
    relationships = _read_attr(page, "relationships") or []
    claims = _read_attr(page, "claims") or []
    questions = _read_attr(page, "questions") or []
    contradictions = _read_attr(page, "contradictions") or []
    confidence = _read_attr(page, "confidence")
    privacy_tier = _read_attr(page, "privacyTier", "privacy_tier")
    updated_at = _read_attr(page, "updatedAt", "updated_at")

    frontmatter: dict[str, Any] = {
        "title": title,
        "kind": kind,
    }
    if isinstance(page_id, str):
        frontmatter["id"] = page_id
    if aliases:
        frontmatter["aliases"] = aliases
    if source_ids:
        frontmatter["sourceIds"] = source_ids
    if relationships:
        frontmatter["relationships"] = [
            {k: v for k, v in rel.__dict__.items() if v is not None} for rel in relationships
        ]
    if claims:
        frontmatter["claims"] = [
            {
                "id": getattr(claim, "id", None),
                "text": getattr(claim, "text", ""),
                "status": getattr(claim, "status", None),
                "evidence": [
                    {k: v for k, v in ev.__dict__.items() if v is not None}
                    for ev in (getattr(claim, "evidence", None) or [])
                ],
            }
            for claim in claims
        ]
    if questions:
        frontmatter["questions"] = questions
    if contradictions:
        frontmatter["contradictions"] = contradictions
    if isinstance(confidence, int | float):
        frontmatter["confidence"] = confidence
    if isinstance(privacy_tier, str):
        frontmatter["privacyTier"] = privacy_tier
    if isinstance(updated_at, str):
        frontmatter["updatedAt"] = updated_at

    related_block = build_related_block(related_pages)
    body = f"# {title}\n\n{related_block}\n"
    return render_wiki_markdown(frontmatter=frontmatter, body=body)


# ruff: noqa: PLR0913, PLR0917 — explicit param list matches OpenClaw guard call


async def _write_one_page_async(
    *,
    vault_root: str,
    page_relative: str,
    body: str,
    page_title: str,
    page_stat: Any,
) -> None:
    """Async worker: write one page under the per-vault mutation lock.

    Mirrors the OpenClaw
    ``refreshPageRelatedBlocks`` write step: the
    ``with_memory_wiki_vault_mutation`` call wraps
    the async ``write_guarded_vault_page`` so
    concurrent compile / apply calls on the same
    vault serialize.
    """

    async def _do_write() -> None:
        await write_guarded_vault_page(
            vault_root=vault_root,
            page_path=page_relative,
            content=body,
            page_stat=page_stat,
            page_label=page_title,
        )

    await with_memory_wiki_vault_mutation(vault_root, _do_write)


@dataclass
class _PendingWrite:
    """The pre-computed per-page write spec.

    Used by ``write_compiled_pages`` to build every
    body up-front (sync), then dispatch the writes
    via a single ``asyncio.run`` so the
    per-vault ``asyncio.Lock`` lives in a single
    event loop.
    """

    page: WikiPageSummary
    page_relative: str
    absolute_path: str
    body: str
    page_title: str
    page_stat: Any
    related_count: int
    written: bool = False
    error: str | None = None


def _build_pending_writes(
    config: ResolvedMemoryWikiConfig,
    pages: list[WikiPageSummary],
) -> list[_PendingWrite]:
    """Pre-compute the per-page write specs (synchronous)."""
    vault_root = config.vault.path
    pending: list[_PendingWrite] = []
    for page in pages:
        related = _resolve_related_pages(page, pages)
        body = build_page_body(page, related)
        page_relative = _read_attr(page, "relativePath", "relative_path") or ""
        absolute = os.path.join(vault_root, page_relative)
        page_stat: Any = None
        if os.path.exists(absolute):
            try:
                page_stat = os.stat(absolute)
            except OSError:
                page_stat = None
        page_title = _read_attr(page, "title") or page_relative
        pending.append(
            _PendingWrite(
                page=page,
                page_relative=page_relative,
                absolute_path=absolute,
                body=body,
                page_title=page_title,
                page_stat=page_stat,
                related_count=len(related),
            )
        )
    return pending


async def _dispatch_pending_writes(
    vault_root: str,
    pending: list[_PendingWrite],
) -> None:
    """Run every pending write inside one event loop.

    Each write goes through
    ``_write_one_page_async`` (which acquires the
    per-vault mutation lock). Per-write exceptions
    are recorded on the spec's ``error`` field so
    one bad page doesn't abort the rest of the
    compile pass.
    """
    for spec in pending:
        try:
            await _write_one_page_async(
                vault_root=vault_root,
                page_relative=spec.page_relative,
                body=spec.body,
                page_title=spec.page_title,
                page_stat=spec.page_stat,
            )
        except Exception as exc:
            spec.error = str(exc)
        else:
            spec.written = True


def write_compiled_pages(
    config: ResolvedMemoryWikiConfig,
    pages: list[WikiPageSummary],
) -> list[PageWriteResult]:
    """Write every scanned page back to disk with the managed blocks refreshed.

    Mirrors the OpenClaw
    ``compileMemoryWikiPages`` write loop. The
    write goes through
    :func:`with_memory_wiki_vault_mutation` so
    concurrent compile / apply calls on the same
    vault serialize.

    The function is sync (the rest of the compile
    pipeline is sync); the per-vault async lock
    inside ``mutation_coordinator`` is driven via
    a single ``asyncio.run`` so the per-vault
    ``asyncio.Lock`` lives in a single event
    loop (avoiding the "lock attached to a
    different loop" error).
    """
    vault_root = config.vault.path
    pending = _build_pending_writes(config, pages)
    asyncio.run(_dispatch_pending_writes(vault_root, pending))
    return [
        PageWriteResult(
            absolute_path=spec.absolute_path,
            relative_path=spec.page_relative,
            written=spec.written,
            related_count=spec.related_count,
            error=spec.error,
        )
        for spec in pending
    ]


__all__ = [
    "HUMAN_END_MARKER",
    "HUMAN_START_MARKER",
    "MAX_RELATED_LINE_LENGTH",
    "MAX_RELATED_PAGES_PER_SECTION",
    "PageWriteResult",
    "WIKI_RELATED_END_MARKER",
    "WIKI_RELATED_START_MARKER",
    "build_page_body",
    "build_related_block",
    "write_compiled_pages",
]
