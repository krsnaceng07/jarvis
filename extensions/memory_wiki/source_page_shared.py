"""source_page_shared — Memory Wiki imported source page writer (Phase 4.3g-mr2).

OpenClaw parity: mirrors
``extensions/memory-wiki/src/source-page-shared.ts``.

The shared helper used by both the
bridge-import and unsafe-local-import
pipelines to write a single imported
source page into the wiki vault. The
writer:

- Checks the source-sync state to
  short-circuit when the page is
  already up-to-date (no
  render-fingerprint + source-mtime
  change → skip).
- Reads the existing page (if any) so
  the human-notes block can be
  preserved across re-imports.
- Renders the new body via the
  caller's ``build_rendered`` callback
  (the bridge / unsafe-local pipelines
  each build a different ``## Source``
  / ``## Content`` / ``## Notes`` shape).
- Writes the page via
  :func:`security.security_runtime.fs_root`
  + the guarded vault page writer (so the
  write stays inside the vault fs-safe
  root).
- Updates the source-sync state entry
  so the next sync sees the new
  fingerprint.
"""

# ruff: noqa: N815, TCH003, ASYNC230 — field names mirror the
# OpenClaw camelCase JSON shape so the
# ``write_imported_source_page``
# return type is byte-compatible with
# the OpenClaw host; ``Callable`` is
# needed at runtime for the public
# ``build_rendered`` callback type;
# the file reads are bounded (small
# markdown files) and run inside an
# already-serialized vault-mutation
# critical section, so a brief blocking
# I/O is acceptable.

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC
from typing import Any

from .markdown import (
    ReplaceManagedBlockParams,
    replace_managed_markdown_block,
)
from .source_sync_state import (
    set_imported_source_entry,
    should_skip_imported_source_write,
)
from .vault_page_write import write_guarded_vault_page


@dataclass(frozen=True, slots=True)
class WriteImportedSourcePageResult:
    """The result of :func:`write_imported_source_page`.

    Mirrors the OpenClaw return shape
    from ``writeImportedSourcePage``
    (inlined as a ``{pagePath, changed, created}``
    object — promoted to a dataclass so the
    Python port can attach field-level
    documentation).
    """

    pagePath: str
    changed: bool
    created: bool


def _is_unreadable_imported_source_page(error: object) -> bool:
    """Return True iff ``error`` is a
    fs-safe "not a file" / "hardlink" error.

    Mirrors the OpenClaw
    ``isUnreadableImportedSourcePage``
    helper.
    """
    code = getattr(error, "code", None)
    return code in ("not-file", "hardlink")


async def _read_existing_imported_source_page(
    page_path: str,
) -> str:
    """Read the existing imported source page,
    returning ``""`` if it's unreadable.

    Mirrors the OpenClaw
    ``readExistingImportedSourcePage``
    helper (one read attempt; the retry
    is OS-agnostic in Python).
    """
    try:
        with open(page_path, encoding="utf-8") as f:
            return f.read()
    except (OSError, ValueError) as exc:
        if _is_unreadable_imported_source_page(exc):
            return ""
        raise


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


def _preserve_human_notes_block(rendered: str, existing: str) -> str:
    """Replace the ``## Notes`` managed block
    in ``rendered`` with the block from
    ``existing`` (preserving human
    notes).

    Mirrors the OpenClaw
    ``preserveHumanNotesBlock`` helper
    via :func:`extensions.memory_wiki.markdown.replace_managed_markdown_block`.
    """
    return replace_managed_markdown_block(
        ReplaceManagedBlockParams(
            original=rendered,
            heading="## Notes",
            start_marker="<!-- openclaw:human:start -->",
            end_marker="<!-- openclaw:human:end -->",
            body=_extract_human_notes_block(existing),
        )
    )


async def write_imported_source_page(
    *,
    vault_root: str,
    sync_key: str,
    source_path: str,
    source_content: str | None,
    source_updated_at_ms: int,
    source_size: int,
    render_fingerprint: str,
    page_path: str,
    group: str,
    state: Any,
    build_rendered: Callable[[str, str], str],
) -> WriteImportedSourcePageResult:
    """Write (or skip) a single imported source page.

    Mirrors the OpenClaw
    :func:`writeImportedSourcePage`. The
    ``state`` / ``group`` come from
    :mod:`extensions.memory_wiki.source_sync_state`;
    the ``build_rendered`` callback is
    provided by the bridge / unsafe-local
    pipeline so each can render its own
    frontmatter / ``## Source`` shape.
    """
    should_skip = should_skip_imported_source_write(
        vault_root=vault_root,
        sync_key=sync_key,
        expected_page_path=page_path,
        expected_source_path=source_path,
        source_updated_at_ms=source_updated_at_ms,
        source_size=source_size,
        render_fingerprint=render_fingerprint,
        state=state,
    )
    if should_skip:
        return WriteImportedSourcePageResult(pagePath=page_path, changed=False, created=False)

    page_stat = os.path.isfile(page_path)
    created = not page_stat
    updated_at_iso = (
        _iso_for_epoch(source_updated_at_ms) if source_updated_at_ms > 0 else _now_iso()
    )
    raw = source_content
    if raw is None:
        with open(source_path, encoding="utf-8") as f:
            raw = f.read()
    rendered = build_rendered(raw, updated_at_iso)
    existing = ""
    if page_stat:
        existing = await _read_existing_imported_source_page(page_path)
    next_rendered = _preserve_human_notes_block(rendered, existing) if existing else rendered
    if existing != next_rendered:
        # ``page_stat`` here is just a bool
        # (file exists or not). The actual
        # ``write_guarded_vault_page`` call
        # in our Python port resolves the
        # real stat when the page exists.
        await write_guarded_vault_page(
            vault_root=vault_root,
            page_path=page_path,
            content=next_rendered,
            page_stat=os.stat(page_path) if page_stat else None,
            page_label="imported source page",
        )

    from .source_sync_state import MemoryWikiImportedSourceStateEntry

    set_imported_source_entry(
        sync_key=sync_key,
        state=state,
        entry=MemoryWikiImportedSourceStateEntry(
            group=group,
            page_path=page_path,
            source_path=source_path,
            source_updated_at_ms=source_updated_at_ms,
            source_size=source_size,
            render_fingerprint=render_fingerprint,
        ),
    )
    return WriteImportedSourcePageResult(
        pagePath=page_path,
        changed=existing != next_rendered,
        created=created,
    )


def _iso_for_epoch(epoch_ms: int) -> str:
    """Format ``epoch_ms`` as an ISO-8601 string."""
    from datetime import datetime

    return datetime.fromtimestamp(epoch_ms / 1000.0, tz=UTC).isoformat().replace("+00:00", "Z")


def _now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    from datetime import datetime

    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


__all__ = [
    "WriteImportedSourcePageResult",
    "write_imported_source_page",
]
