"""okf — Memory Wiki Open Knowledge Format import (Phase 4.3g-mr5).

OpenClaw parity: mirrors
``extensions/memory-wiki/src/okf.ts``.

The OKF import pipeline walks an unpacked
OKF bundle directory and writes one
``concepts/<page>.md`` page per concept
document. The page is the same shape as
the OpenClaw `concept` page kind, with
the ``okfConceptId`` + ``okfType`` +
``sourceIds: [source.okf.<bundleKey>]``
frontmatter that lets a later compile
pass cross-link the bundle to the rest
of the wiki.

The pipeline also prunes any
``concepts/<page>.md`` whose
``okf.bundleKey`` matches the import but
whose ``pagePath`` is no longer in the
incoming set (a concept was dropped from
the bundle between imports).
"""

# ruff: noqa: N815, PLR0915, ASYNC230, S324 — field names mirror the
# OpenClaw camelCase JSON shape; the
# bundle walk + page write loop mirrors
# OpenClaw's exhaustive ladder; the file
# reads are bounded (small markdown files
# per concept) and run inside the
# import's mutation critical section;
# SHA-1 fingerprinting is OpenClaw's
# choice (stable short digest).

from __future__ import annotations

import hashlib
import os
import posixpath
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from jarvis_sdk import (
    normalize_optional_string,
    normalize_single_or_trimmed_string_list,
    unique_strings,
)

from .compile_pipeline import compile_wiki_vault
from .log import append_memory_wiki_log
from .markdown import parse_wiki_frontmatter
from .markdown_pages import (
    create_wiki_page_filename,
    render_wiki_markdown,
    slugify_wiki_segment,
)
from .time import resolve_memory_wiki_timestamp
from .vault import initialize_memory_wiki_vault
from .vault_page_write import write_guarded_vault_page

if TYPE_CHECKING:
    from .config import ResolvedMemoryWikiConfig


# Mirrors the OpenClaw
# ``OKF_RESERVED_FILENAMES`` set.
OKF_RESERVED_FILENAMES: frozenset[str] = frozenset({"index.md", "log.md"})

# Mirrors the OpenClaw
# ``OKF_MARKDOWN_LINK_PATTERN`` regex.
OKF_MARKDOWN_LINK_PATTERN: re.Pattern[str] = re.compile(r"(!?)\[([^\]]*)\]\(([^)]+)\)")

# Mirrors the OpenClaw
# ``OKF_FENCE_PATTERN`` regex.
OKF_FENCE_PATTERN: re.Pattern[str] = re.compile(r"^ {0,3}(`{3,}|~{3,})")

# Mirrors the OpenClaw
# ``OKF_HASH_CHARS`` constant.
OKF_HASH_CHARS = 8


@dataclass(frozen=True, slots=True)
class OkfConceptDocument:
    """A single OKF concept document.

    Mirrors the OpenClaw ``OkfConceptDocument``
    type. Field names are camelCase.
    """

    conceptId: str
    relativePath: str
    absolutePath: str
    frontmatter: dict[str, Any]
    body: str
    type: str
    title: str
    description: str | None = None
    resource: str | None = None
    tags: list[str] = field(default_factory=list)
    timestamp: str | None = None


@dataclass(frozen=True, slots=True)
class ImportMemoryWikiOkfWarning:
    """A warning emitted during OKF import.

    Mirrors the OpenClaw
    ``ImportMemoryWikiOkfWarning`` type.
    """

    code: str
    path: str
    message: str


@dataclass(frozen=True, slots=True)
class ImportMemoryWikiOkfResult:
    """The result of
    :func:`import_memory_wiki_okf_bundle`.

    Mirrors the OpenClaw
    ``ImportMemoryWikiOkfResult`` type.
    """

    bundlePath: str
    bundleName: str
    okfVersion: str | None = None
    importedCount: int = 0
    updatedCount: int = 0
    removedCount: int = 0
    skippedCount: int = 0
    pagePaths: list[str] = field(default_factory=list)
    removedPagePaths: list[str] = field(default_factory=list)
    warnings: list[ImportMemoryWikiOkfWarning] = field(default_factory=list)
    indexUpdatedFiles: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class OkfBundleMetadata:
    """The bundle-level metadata parsed from
    ``index.md`` + the bundle directory.

    Mirrors the OpenClaw ``OkfBundleMetadata``
    type.
    """

    key: str
    version: str | None = None


def to_posix_path(value: str) -> str:
    """Convert ``value`` to a POSIX-style path.

    Mirrors the OpenClaw ``toPosixPath``
    helper.
    """
    if os.sep == "/":
        return value
    return "/".join(value.split(os.sep))


def trim_markdown_extension(value: str) -> str:
    """Strip a trailing ``.md`` from ``value``.

    Mirrors the OpenClaw
    ``trimMarkdownExtension`` helper.
    """
    return re.sub(r"\.md$", "", value, flags=re.IGNORECASE)


def _create_okf_bundle_key(
    *,
    root_frontmatter: dict[str, Any],
    bundle_name: str,
    bundle_path: str,
) -> str:
    """Compute a stable bundle key.

    Mirrors the OpenClaw
    ``createOkfBundleKey`` helper. Prefers
    an explicit ``id`` / ``okf_id`` in the
    root frontmatter; otherwise derives
    a slug from the bundle name + a
    SHA-1 hash of the bundle path.
    """
    producer_id = normalize_optional_string(
        root_frontmatter.get("id")
    ) or normalize_optional_string(root_frontmatter.get("okf_id"))
    if producer_id:
        return slugify_wiki_segment(producer_id)
    label = (
        normalize_optional_string(root_frontmatter.get("name"))
        or normalize_optional_string(root_frontmatter.get("title"))
        or bundle_name
    )
    digest = hashlib.sha1(bundle_path.encode("utf-8")).hexdigest()[:OKF_HASH_CHARS]
    return f"{slugify_wiki_segment(label)}-{digest}"


def _create_okf_page_stem(bundle_key: str, concept_id: str) -> str:
    """Compute the per-concept page stem.

    Mirrors the OpenClaw
    ``createOkfPageStem`` helper.
    """
    slug = slugify_wiki_segment(concept_id.replace("/", "-"))
    digest = hashlib.sha1(concept_id.encode("utf-8")).hexdigest()[:OKF_HASH_CHARS]
    return f"okf-{bundle_key}-{slug}-{digest}"


def _create_okf_page_identity(bundle_key: str, concept_id: str) -> dict[str, str]:
    """Compute the per-concept ``pageId`` +
    ``pagePath``.

    Mirrors the OpenClaw
    ``createOkfPageIdentity`` helper.
    """
    file_name = create_wiki_page_filename(_create_okf_page_stem(bundle_key, concept_id))
    stem = trim_markdown_extension(file_name)
    return {
        "pageId": f"concept.{stem}",
        "pagePath": f"concepts/{file_name}",
    }


def _collect_okf_markdown_files(
    root_dir: str,
    warnings: list[ImportMemoryWikiOkfWarning],
) -> list[str]:
    """Recursively collect every ``.md`` file
    under ``root_dir`` (sorted, POSIX-style
    paths), excluding ``.git`` /
    ``node_modules`` directories.

    Mirrors the OpenClaw
    ``collectOkfMarkdownFiles`` helper.
    """

    def walk(relative_dir: str) -> list[str]:
        absolute_dir = os.path.join(root_dir, relative_dir)
        try:
            entries = sorted(
                os.listdir(absolute_dir),
                key=lambda name: name,
            )
        except OSError as err:
            warnings.append(
                ImportMemoryWikiOkfWarning(
                    code="unreadable-entry",
                    path=to_posix_path(relative_dir) or ".",
                    message=str(err),
                )
            )
            return []
        files: list[str] = []
        for entry in entries:
            if entry in (".git", "node_modules"):
                continue
            relative_path = os.path.join(relative_dir, entry)
            full_path = os.path.join(absolute_dir, entry)
            if os.path.isdir(full_path):
                files.extend(walk(relative_path))
                continue
            if os.path.isfile(full_path) and entry.endswith(".md"):
                files.append(relative_path)
        return files

    raw = walk("")
    return sorted(to_posix_path(p) for p in raw)


def _parse_okf_markdown(content: str, relative_path: str) -> dict[str, Any]:
    """Parse an OKF concept file.

    Mirrors the OpenClaw
    ``parseOkfMarkdown`` helper. Returns
    a dict with ``frontmatter`` + ``body``
    + an optional ``warning`` (the
    :class:`ImportMemoryWikiOkfWarning`).
    """
    normalized_content = content.replace("\r\n", "\n")
    try:
        parsed = parse_wiki_frontmatter(normalized_content)
        return {
            "frontmatter": parsed.frontmatter,
            "body": parsed.body,
        }
    except (ValueError, KeyError) as err:
        return {
            "frontmatter": {},
            "body": normalized_content,
            "warning": ImportMemoryWikiOkfWarning(
                code="invalid-concept",
                path=relative_path,
                message=str(err),
            ),
        }


def _read_okf_text_file(
    *,
    bundle_path: str,
    relative_path: str,
    warnings: list[ImportMemoryWikiOkfWarning],
) -> str | None:
    """Read the OKF concept file at
    ``bundle_path/relative_path``.

    Mirrors the OpenClaw
    ``readOkfTextFile`` helper. Returns
    ``None`` if the file is missing or
    unreadable; appends a warning.
    """
    full_path = os.path.join(bundle_path, relative_path)
    try:
        with open(full_path, encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        warnings.append(
            ImportMemoryWikiOkfWarning(
                code="unreadable-entry",
                path=relative_path,
                message="OKF concept file is missing.",
            )
        )
        return None
    except OSError as err:
        warnings.append(
            ImportMemoryWikiOkfWarning(
                code="unreadable-entry",
                path=relative_path,
                message=str(err),
            )
        )
        return None


def _derive_okf_title(relative_path: str, frontmatter: dict[str, Any]) -> str:
    """Derive the concept title from the
    frontmatter + the file name.

    Mirrors the OpenClaw
    ``deriveOkfTitle`` helper.
    """
    title = normalize_optional_string(frontmatter.get("title"))
    if title:
        return title
    base = posixpath.basename(relative_path).removesuffix(".md")
    fallback = re.sub(r"[-_]+", " ", base).strip()
    return fallback or trim_markdown_extension(relative_path)


def _normalize_okf_concept(
    *,
    bundle_path: str,
    relative_path: str,
    content: str,
) -> dict[str, Any]:
    """Normalize an OKF concept into the
    :class:`OkfConceptDocument` shape.

    Mirrors the OpenClaw
    ``normalizeOkfConcept`` helper. Returns
    a dict with an optional ``concept`` +
    an optional ``warning``.
    """
    parsed = _parse_okf_markdown(content, relative_path)
    if "warning" in parsed:
        return {"warning": parsed["warning"]}

    concept_type = normalize_optional_string(parsed["frontmatter"].get("type"))
    if not concept_type:
        return {
            "warning": ImportMemoryWikiOkfWarning(
                code="missing-type",
                path=relative_path,
                message=("OKF concept is missing required non-empty type frontmatter."),
            )
        }

    concept_id = trim_markdown_extension(relative_path)
    timestamp = normalize_optional_string(parsed["frontmatter"].get("timestamp"))
    description = normalize_optional_string(parsed["frontmatter"].get("description"))
    resource = normalize_optional_string(parsed["frontmatter"].get("resource"))
    tags = normalize_single_or_trimmed_string_list(parsed["frontmatter"].get("tags", []))
    title = _derive_okf_title(relative_path, parsed["frontmatter"])

    concept = OkfConceptDocument(
        conceptId=concept_id,
        relativePath=relative_path,
        absolutePath=os.path.join(bundle_path, relative_path),
        frontmatter=parsed["frontmatter"],
        body=parsed["body"],
        type=concept_type,
        title=title,
        description=description,
        resource=resource,
        tags=list(tags),
        timestamp=timestamp,
    )
    return {"concept": concept}


def _split_markdown_link_destination(target: str) -> dict[str, str]:
    """Split a markdown link target into
    ``destination`` + ``titleSuffix``.

    Mirrors the OpenClaw
    ``splitMarkdownLinkDestination``
    helper.
    """
    trimmed = target.strip()
    if trimmed.startswith("<"):
        end = trimmed.find(">")
        if end > 0:
            return {
                "destination": trimmed[1:end],
                "titleSuffix": trimmed[end + 1 :],
            }
    match = re.match(r"^(\S+)(\s+[\s\S]+)?$", trimmed)
    if match is None:
        return {"destination": trimmed, "titleSuffix": ""}
    return {
        "destination": match.group(1) or trimmed,
        "titleSuffix": match.group(2) or "",
    }


def _safe_decode_okf_link_path(value: str | None) -> str:
    """URL-decode ``value`` if possible.

    Mirrors the OpenClaw
    ``safeDecodeOkfLinkPath`` helper.
    """
    if not value:
        return ""
    from urllib.parse import unquote

    try:
        return unquote(value)
    except (ValueError, UnicodeDecodeError):
        return value


def _resolve_okf_markdown_target(source_relative_path: str, target: str) -> str | None:
    """Resolve a markdown link ``target`` into
    a bundle-local ``conceptId``.

    Mirrors the OpenClaw
    ``resolveOkfMarkdownTarget`` helper.
    Returns ``None`` for external links,
    fragments-only links, or links that
    escape the bundle root.
    """
    parts = _split_markdown_link_destination(target)
    trimmed = parts["destination"].strip()
    if (
        not trimmed
        or trimmed.startswith("#")
        or re.match(r"^[a-z][a-z0-9+.-]*:", trimmed, flags=re.IGNORECASE)
    ):
        return None

    raw = trimmed.split("#", 1)[0].split("?", 1)[0].replace("\\", "/").strip()
    decoded = _safe_decode_okf_link_path(raw)
    if not decoded or not decoded.endswith(".md"):
        return None

    if decoded.startswith("/"):
        normalized = posixpath.normpath(decoded[1:])
    else:
        normalized = posixpath.normpath(
            posixpath.join(posixpath.dirname(source_relative_path), decoded)
        )
    concept_id = trim_markdown_extension(normalized)
    if concept_id.startswith("../"):
        return None
    return concept_id


def _get_markdown_destination_suffix(destination: str) -> str:
    """Return the ``?query`` / ``#fragment``
    suffix from ``destination``.

    Mirrors the OpenClaw
    ``getMarkdownDestinationSuffix``
    helper.
    """
    query_index = destination.find("?")
    fragment_index = destination.find("#")
    if query_index == -1:
        suffix_index = fragment_index
    elif fragment_index == -1:
        suffix_index = query_index
    else:
        suffix_index = min(query_index, fragment_index)
    return "" if suffix_index == -1 else destination[suffix_index:]


def _rewrite_markdown_line_outside_inline_code(
    line: str,
    rewrite_links: Any,
) -> str:
    """Rewrite markdown links on ``line``,
    but skip inline code spans.

    Mirrors the OpenClaw
    ``rewriteMarkdownLineOutsideInlineCode``
    helper.
    """
    result: list[str] = []
    cursor = 0
    while cursor < len(line):
        code_start = line.find("`", cursor)
        if code_start == -1:
            result.append(rewrite_links(line[cursor:]))
            break
        result.append(rewrite_links(line[cursor:code_start]))
        match = re.match(r"^`+", line[code_start:])
        delimiter = match.group(0) if match else "`"
        code_end = line.find(delimiter, code_start + len(delimiter))
        if code_end == -1:
            result.append(line[code_start:])
            break
        result.append(line[code_start : code_end + len(delimiter)])
        cursor = code_end + len(delimiter)
    return "".join(result)


def _rewrite_markdown_outside_code(
    markdown: str,
    rewrite_links: Any,
) -> str:
    """Rewrite markdown links in ``markdown``,
    skipping code fences and inline code.

    Mirrors the OpenClaw
    ``rewriteMarkdownOutsideCode`` helper.
    """
    lines = re.split(r"(\n)", markdown)
    in_fence = False
    fence_delimiter = ""
    output: list[str] = []
    for line in lines:
        if line == "\n":
            output.append(line)
            continue
        fence_match = OKF_FENCE_PATTERN.match(line)
        if fence_match:
            delimiter = fence_match.group(1) or ""
            closes_fence = (
                in_fence
                and delimiter.startswith((fence_delimiter or " ")[0])
                and len(delimiter) >= len(fence_delimiter)
            )
            if not in_fence:
                in_fence = True
                fence_delimiter = delimiter
            elif closes_fence:
                in_fence = False
                fence_delimiter = ""
            output.append(line)
            continue
        if in_fence:
            output.append(line)
        else:
            output.append(_rewrite_markdown_line_outside_inline_code(line, rewrite_links))
    return "".join(output)


def _rewrite_okf_markdown_links(
    *,
    body: str,
    source_page_path: str,
    source_relative_path: str,
    page_by_concept_id: dict[str, dict[str, str]],
) -> dict[str, Any]:
    """Rewrite in-bundle markdown links
    inside ``body`` to the per-concept
    page path.

    Mirrors the OpenClaw
    ``rewriteOkfMarkdownLinks`` helper.
    """
    linked_concept_ids: list[str] = []

    def rewrite_links(markdown: str) -> str:
        return OKF_MARKDOWN_LINK_PATTERN.sub(
            lambda match: _rewrite_one_link(
                match,
                source_relative_path=source_relative_path,
                source_page_path=source_page_path,
                page_by_concept_id=page_by_concept_id,
                linked_concept_ids=linked_concept_ids,
            ),
            markdown,
        )

    rewritten = _rewrite_markdown_outside_code(body, rewrite_links)
    return {
        "body": rewritten,
        "linkedConceptIds": unique_strings(linked_concept_ids),
    }


def _rewrite_one_link(
    match: re.Match[str],
    *,
    source_relative_path: str,
    source_page_path: str,
    page_by_concept_id: dict[str, dict[str, str]],
    linked_concept_ids: list[str],
) -> str:
    """Helper for :func:`_rewrite_okf_markdown_links`.

    Mirrors the OpenClaw closure inside
    ``rewriteOkfMarkdownLinks``.
    """
    image_prefix = match.group(1) or ""
    label = match.group(2) or ""
    raw_target = match.group(3) or ""
    concept_id = _resolve_okf_markdown_target(source_relative_path, raw_target)
    if not concept_id:
        return match.group(0)
    target = page_by_concept_id.get(concept_id)
    if not target:
        return match.group(0)
    linked_concept_ids.append(concept_id)
    parts = _split_markdown_link_destination(raw_target)
    relative_target = posixpath.relpath(posixpath.dirname(source_page_path), target["pagePath"])
    suffix = _get_markdown_destination_suffix(parts["destination"])
    return f"{image_prefix}[{label}]({relative_target}{suffix}{parts['titleSuffix']})"


def _read_root_okf_metadata(
    *,
    root_index: str | None,
    bundle_name: str,
    bundle_path: str,
) -> OkfBundleMetadata:
    """Read the bundle-level metadata.

    Mirrors the OpenClaw
    ``readRootOkfMetadata`` helper.
    """
    if not root_index:
        return OkfBundleMetadata(
            key=_create_okf_bundle_key(
                root_frontmatter={},
                bundle_name=bundle_name,
                bundle_path=bundle_path,
            )
        )
    parsed = _parse_okf_markdown(root_index, "index.md")
    version = normalize_optional_string(parsed["frontmatter"].get("okf_version"))
    return OkfBundleMetadata(
        key=_create_okf_bundle_key(
            root_frontmatter=parsed["frontmatter"],
            bundle_name=bundle_name,
            bundle_path=bundle_path,
        ),
        version=version,
    )


async def _write_okf_concept_page(
    *,
    vault_root: str,
    page_path: str,
    content: str,
) -> dict[str, bool]:
    """Write a concept page to ``vault_root``
    if it differs from the existing copy.

    Mirrors the OpenClaw
    ``writeOkfConceptPage`` helper. Returns
    ``{"changed": bool, "created": bool}``.
    """
    full_path = os.path.join(vault_root, page_path)
    existing = ""
    page_existed = False
    page_stat: Any = None
    if os.path.isfile(full_path):
        page_existed = True
        try:
            with open(full_path, encoding="utf-8") as f:
                existing = f.read()
        except OSError:
            existing = ""

    if existing == content or _normalize_okf_rendered_page_for_comparison(
        existing
    ) == _normalize_okf_rendered_page_for_comparison(content):
        return {"changed": False, "created": not page_existed}

    await write_guarded_vault_page(
        vault_root=vault_root,
        page_path=page_path,
        content=content,
        page_stat=page_stat,
        page_label="OKF concept page",
    )
    return {"changed": True, "created": not page_existed}


def _normalize_okf_rendered_page_for_comparison(content: str) -> str:
    """Normalize a rendered OKF page for
    equality comparison.

    Mirrors the OpenClaw
    ``normalizeOkfRenderedPageForComparison``
    helper. Strips the auto-generated
    ``## Related`` block + the volatile
    ``importedAt`` / ``updatedAt``
    frontmatter fields.
    """
    from .markdown import WIKI_RELATED_END_MARKER, WIKI_RELATED_START_MARKER

    related_pattern = re.compile(
        r"\n+## Related\n"
        + re.escape(WIKI_RELATED_START_MARKER)
        + r"[\s\S]*?"
        + re.escape(WIKI_RELATED_END_MARKER)
        + r"\n?",
        flags=re.MULTILINE,
    )
    without_related = related_pattern.sub("\n", content)
    frontmatter_match = re.match(r"^---\n([\s\S]*?)\n---\n?", without_related)
    if not frontmatter_match:
        return without_related.rstrip()
    frontmatter_body = frontmatter_match.group(1) or ""
    volatile = re.sub(r"^(?:importedAt|updatedAt): .*\n", "", frontmatter_body, flags=re.MULTILINE)
    if not volatile.endswith("\n"):
        volatile = volatile + "\n"
    return (f"---\n{volatile}---\n{without_related[frontmatter_match.end():]}").rstrip()


def _remove_stale_okf_concept_pages(
    *,
    vault_root: str,
    bundle_key: str,
    current_page_paths: set[str],
) -> list[str]:
    """Remove OKF concept pages for
    ``bundle_key`` whose ``pagePath`` is
    not in ``current_page_paths``.

    Mirrors the OpenClaw
    ``removeStaleOkfConceptPages`` helper.
    """
    concepts_dir = os.path.join(vault_root, "concepts")
    if not os.path.isdir(concepts_dir):
        return []
    removed: list[str] = []
    for entry in sorted(os.listdir(concepts_dir)):
        if not entry.endswith(".md") or entry == "index.md":
            continue
        page_path = f"concepts/{entry}"
        if page_path in current_page_paths:
            continue
        full_path = os.path.join(concepts_dir, entry)
        if not os.path.isfile(full_path):
            continue
        try:
            with open(full_path, encoding="utf-8") as f:
                raw = f.read()
        except OSError:
            continue
        try:
            parsed = parse_wiki_frontmatter(raw)
        except (ValueError, KeyError):
            continue
        okf = parsed.frontmatter.get("okf")
        if isinstance(okf, dict) and okf.get("bundleKey") == bundle_key:
            try:
                os.remove(full_path)
            except OSError:
                continue
            removed.append(page_path)
    return removed


def format_okf_import_summary(result: ImportMemoryWikiOkfResult) -> str:
    """Return a human-readable summary line
    for the OKF import.

    Mirrors the OpenClaw
    ``formatOkfImportSummary`` helper.
    """
    return (
        f"Imported {result.importedCount} OKF concept"
        f"{'' if result.importedCount == 1 else 's'} from {result.bundlePath} "
        f"into memory wiki. Updated {result.updatedCount}; "
        f"removed {result.removedCount}; "
        f"skipped {result.skippedCount}; "
        f"refreshed {len(result.indexUpdatedFiles)} index file"
        f"{'' if len(result.indexUpdatedFiles) == 1 else 's'}."
    )


async def import_memory_wiki_okf_bundle(  # noqa: PLR0912 — mirrors OpenClaw's exhaustive ladder
    *,
    config: ResolvedMemoryWikiConfig,
    bundle_path: str,
    now_ms: int | None = None,
) -> ImportMemoryWikiOkfResult:
    """Import an OKF bundle into the wiki
    vault at ``config.vault.path``.

    Mirrors the OpenClaw
    ``importMemoryWikiOkfBundle`` function.
    """
    initialize_memory_wiki_vault(config, now_ms=now_ms)
    bundle_path_abs = os.path.abspath(bundle_path)
    if not os.path.isdir(bundle_path_abs):
        raise ValueError("wiki okf import expects an unpacked OKF bundle directory.")

    warnings: list[ImportMemoryWikiOkfWarning] = []
    markdown_files = _collect_okf_markdown_files(bundle_path_abs, warnings)
    concepts: list[OkfConceptDocument] = []
    root_index_content: str | None = None

    for relative_path in markdown_files:
        if relative_path == "index.md":
            root_index_content = _read_okf_text_file(
                bundle_path=bundle_path_abs,
                relative_path=relative_path,
                warnings=warnings,
            )
        if posixpath.basename(relative_path) in OKF_RESERVED_FILENAMES:
            continue
        content = _read_okf_text_file(
            bundle_path=bundle_path_abs,
            relative_path=relative_path,
            warnings=warnings,
        )
        if content is None:
            continue
        normalized = _normalize_okf_concept(
            bundle_path=bundle_path_abs,
            relative_path=relative_path,
            content=content,
        )
        if "warning" in normalized:
            warnings.append(normalized["warning"])  # type: ignore[arg-type]
            continue
        if "concept" in normalized:
            concepts.append(normalized["concept"])  # type: ignore[arg-type]

    timestamp = resolve_memory_wiki_timestamp(now_ms)
    bundle_name = os.path.basename(bundle_path_abs)
    bundle_metadata = _read_root_okf_metadata(
        root_index=root_index_content,
        bundle_name=bundle_name,
        bundle_path=bundle_path_abs,
    )
    bundle_key = bundle_metadata.key
    page_by_concept_id: dict[str, dict[str, str]] = {}
    for concept in concepts:
        page_identity = _create_okf_page_identity(bundle_key, concept.conceptId)
        page_by_concept_id[concept.conceptId] = {
            "pageId": page_identity["pageId"],
            "pagePath": page_identity["pagePath"],
            "title": concept.title,
        }

    imported_pages: list[dict[str, Any]] = []
    updated_count = 0
    os.makedirs(os.path.join(config.vault.path, "concepts"), exist_ok=True)
    for concept in sorted(concepts, key=lambda c: c.conceptId):
        page = page_by_concept_id.get(concept.conceptId)
        if not page:
            continue
        rewritten = _rewrite_okf_markdown_links(
            body=concept.body,
            source_page_path=page["pagePath"],
            source_relative_path=concept.relativePath,
            page_by_concept_id=page_by_concept_id,
        )
        relationships = [
            {
                "targetId": page_by_concept_id[cid]["pageId"],
                "targetPath": page_by_concept_id[cid]["pagePath"],
                "targetTitle": page_by_concept_id[cid]["title"],
                "kind": "okf-link",
                "evidenceKind": "okf-markdown-link",
            }
            for cid in rewritten["linkedConceptIds"]
            if cid in page_by_concept_id
        ]
        frontmatter: dict[str, Any] = {
            "pageType": "concept",
            "id": page["pageId"],
            "title": concept.title,
            "sourceType": "okf",
            "provenanceMode": "okf-import",
            "sourcePath": concept.absolutePath,
            "okfConceptId": concept.conceptId,
            "okfType": concept.type,
            "sourceIds": [f"source.okf.{bundle_key}"],
            "importedAt": timestamp,
            "updatedAt": concept.timestamp or timestamp,
            "status": "active",
        }
        if concept.description:
            frontmatter["description"] = concept.description
        if concept.resource:
            frontmatter["resource"] = concept.resource
        if concept.tags:
            frontmatter["tags"] = list(concept.tags)
        if concept.timestamp:
            frontmatter["okfTimestamp"] = concept.timestamp
        if relationships:
            frontmatter["relationships"] = relationships
        frontmatter["okf"] = {
            **({"version": bundle_metadata.version} if bundle_metadata.version else {}),
            "bundleName": bundle_name,
            "bundleKey": bundle_key,
            "conceptId": concept.conceptId,
            "sourceRelativePath": concept.relativePath,
            "frontmatter": concept.frontmatter,
        }
        write_result = await _write_okf_concept_page(
            vault_root=config.vault.path,
            page_path=page["pagePath"],
            content=render_wiki_markdown(
                frontmatter=frontmatter,
                body=rewritten["body"],
            ),
        )
        if not write_result["created"] and write_result["changed"]:
            updated_count += 1
        imported_pages.append(
            {
                "conceptId": concept.conceptId,
                "sourcePath": concept.absolutePath,
                "pageId": page["pageId"],
                "pagePath": page["pagePath"],
                "title": concept.title,
                "created": write_result["created"],
            }
        )
    current_page_paths = {p["pagePath"] for p in imported_pages}
    removed_page_paths = (
        []
        if warnings
        else _remove_stale_okf_concept_pages(
            vault_root=config.vault.path,
            bundle_key=bundle_key,
            current_page_paths=current_page_paths,
        )
    )

    append_memory_wiki_log(
        config.vault.path,
        {
            "type": "okf-import",
            "details": {
                "bundlePath": bundle_path_abs,
                "bundleName": bundle_name,
                "importedCount": len(imported_pages),
                "updatedCount": updated_count,
                "removedCount": len(removed_page_paths),
                "skippedCount": len(warnings),
                "pagePaths": [p["pagePath"] for p in imported_pages],
                "removedPagePaths": removed_page_paths,
            },
        },
    )

    compile_result = compile_wiki_vault(config)
    return ImportMemoryWikiOkfResult(
        bundlePath=bundle_path_abs,
        bundleName=bundle_name,
        okfVersion=bundle_metadata.version,
        importedCount=len(imported_pages),
        updatedCount=updated_count,
        removedCount=len(removed_page_paths),
        skippedCount=len(warnings),
        pagePaths=[p["pagePath"] for p in imported_pages],
        removedPagePaths=removed_page_paths,
        warnings=warnings,
        indexUpdatedFiles=[page.absolute_path for page in compile_result.pages],
    )


__all__ = [
    "ImportMemoryWikiOkfResult",
    "ImportMemoryWikiOkfWarning",
    "OKF_FENCE_PATTERN",
    "OKF_MARKDOWN_LINK_PATTERN",
    "OKF_RESERVED_FILENAMES",
    "OkfBundleMetadata",
    "OkfConceptDocument",
    "format_okf_import_summary",
    "import_memory_wiki_okf_bundle",
    "to_posix_path",
    "trim_markdown_extension",
]
