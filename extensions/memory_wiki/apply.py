"""apply — Memory Wiki mutation apply path.

OpenClaw parity: mirrors
``extensions/memory-wiki/src/apply.ts``.

The apply path implements the two write
operations the memory-wiki tools expose:

- ``create_synthesis`` — create a new
  synthesis page under ``syntheses/`` from
  user-supplied title + body + source ids.
  Re-uses the existing page's frontmatter
  (if any) so the synthesis picks up the
  operator's prior notes; always rewrites
  the ``## Summary`` managed block via
  :func:`markdown.replace_managed_markdown_block`;
  preserves the ``## Notes`` human-notes
  block via :func:`_ensure_human_notes_block`.

- ``update_metadata`` — patch the
  frontmatter of an existing page (looked
  up by ``lookup``). The body is preserved
  verbatim; only the frontmatter fields
  listed in the mutation are touched.

Both mutations are wrapped in
:func:`mutation_coordinator.with_memory_wiki_vault_mutation`
so concurrent compile / apply calls on the
same vault serialize. After every successful
mutation, the compile pipeline is re-run so
the compiled cache + dashboards reflect the
new state.

The :func:`normalize_memory_wiki_mutation_input`
helper validates + normalizes the raw input
the tool layer hands in. The same alias
shortcuts the OpenClaw source accepts
(``op: "synthesis"`` → ``op: "create_synthesis"``,
``op: "metadata"`` → ``op: "update_metadata"``)
are preserved.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

from jarvis_sdk import (
    FsSafeError,
    fs_root,
    normalize_optional_string,
    normalize_string_entries,
    unique_strings,
)

from . import markdown
from .compile_pipeline import compile_wiki_vault
from .markdown_pages import (
    normalize_source_ids,
    normalize_wiki_claims,
    render_wiki_markdown,
    slugify_wiki_page_stem,
    slugify_wiki_segment,
)
from .mutation_coordinator import with_memory_wiki_vault_mutation
from .query import (
    read_queryable_wiki_pages,
    resolve_queryable_wiki_page_by_lookup,
)
from .vault import initialize_memory_wiki_vault

if TYPE_CHECKING:
    from .config import ResolvedMemoryWikiConfig


# Mirrors the OpenClaw ``GENERATED_START`` /
# ``GENERATED_END`` / ``HUMAN_START`` /
# ``HUMAN_END`` constants used by the
# apply path.
GENERATED_START_MARKER = "<!-- openclaw:wiki:generated:start -->"
GENERATED_END_MARKER = "<!-- openclaw:wiki:generated:end -->"
HUMAN_START_MARKER = "<!-- openclaw:human:start -->"
HUMAN_END_MARKER = "<!-- openclaw:human:end -->"


MutationOp = Literal["create_synthesis", "update_metadata"]
# Input alias shortcuts the OpenClaw source
# accepts. ``synthesis`` → ``create_synthesis``;
# ``metadata`` → ``update_metadata``.
MutationInputOp = MutationOp | Literal["synthesis", "metadata"]


# ── mutation dataclasses ─────────────────────────────────


@dataclass(frozen=True, slots=True)
class CreateSynthesisMutation:
    """A ``create_synthesis`` mutation.

    Mirrors the OpenClaw
    ``CreateSynthesisMemoryWikiMutation`` shape.
    """

    title: str
    body: str
    source_ids: list[str]
    op: Literal["create_synthesis"] = "create_synthesis"
    claims: list[dict[str, Any]] = field(default_factory=list)
    contradictions: list[str] = field(default_factory=list)
    questions: list[str] = field(default_factory=list)
    confidence: float | None = None
    status: str | None = None


@dataclass(frozen=True, slots=True)
class UpdateMetadataMutation:
    """An ``update_metadata`` mutation.

    Mirrors the OpenClaw
    ``UpdateMetadataMemoryWikiMutation`` shape.
    The optional fields default to ``None``
    (not provided → keep existing value);
    use ``confidence=None`` to *clear* the
    field (the OpenClaw ``null`` sentinel).
    """

    lookup: str
    op: Literal["update_metadata"] = "update_metadata"
    source_ids: list[str] | None = None
    claims: list[dict[str, Any]] | None = None
    contradictions: list[str] | None = None
    questions: list[str] | None = None
    confidence: float | None | Literal["__unset__"] = "__unset__"
    status: str | None = None


ApplyMutation = CreateSynthesisMutation | UpdateMetadataMutation


@dataclass(frozen=True, slots=True)
class ApplyMutationResult:
    """The result of :func:`apply_memory_wiki_mutation`.

    Mirrors the OpenClaw
    ``ApplyMemoryWikiMutationResult`` shape.
    """

    changed: bool
    operation: MutationOp
    page_path: str
    page_id: str | None = None
    # Compile result populated by the apply
    # path (the OpenClaw source embeds the
    # full ``CompileMemoryWikiResult``; the
    # Python port keeps a slim version that
    # the gateway / tool layers can inspect).
    scanned_count: int = 0
    invalid_count: int = 0
    ignored_count: int = 0


# Sentinel for distinguishing ``confidence
# not provided`` from ``confidence = None``
# (the OpenClaw source uses ``null`` for the
# latter). The Python port can't reuse
# ``None`` because that's the
# not-provided marker too.
_UNSET: Any = "__unset__"


# ── normalization helpers ────────────────────────────────


def _normalize_mutation_confidence(
    params: dict[str, Any],
    *,
    allow_null: bool,
) -> float | None:
    """Validate + clamp the ``confidence`` field.

    Mirrors the OpenClaw
    ``normalizeMutationConfidence``. When
    ``allow_null`` is True, a ``None`` /
    ``null`` value is preserved (the OpenClaw
    sentinel for "clear this field"); the
    caller distinguishes ``not provided`` from
    ``explicit null`` via the
    ``_UNSET`` sentinel. When ``allow_null``
    is False, ``None`` is treated as
    "not provided" (returns ``None``).
    """
    confidence = params.get("confidence", _UNSET)
    if confidence is _UNSET:
        return None
    if confidence is None:
        if allow_null:
            return None
        return None
    if isinstance(confidence, bool):
        # ``bool`` is a subclass of ``int`` in
        # Python; reject explicitly (matches
        # OpenClaw's finite-number check).
        return None
    if (
        isinstance(confidence, int | float)
        and confidence == confidence  # noqa: PLR0124 — canonical NaN check
        and 0 <= confidence <= 1
    ):
        return float(confidence)
    return None


def _normalize_mutation_op(op: str) -> MutationOp:
    """Map input ``op`` strings to the canonical mutation op.

    Mirrors the OpenClaw
    ``normalizeMemoryWikiMutationOp``.
    """
    if op == "synthesis":
        return "create_synthesis"
    if op == "metadata":
        return "update_metadata"
    return op  # type: ignore[return-value]


def normalize_memory_wiki_mutation_input(
    raw_params: Any,
) -> ApplyMutation:
    """Validate + normalize a raw mutation input.

    Mirrors the OpenClaw
    ``normalizeMemoryWikiMutationInput``.
    Raises ``ValueError`` when the input is
    missing a required field.
    """
    if not isinstance(raw_params, dict):
        raise ValueError("wiki mutation requires an object input")
    op_raw = raw_params.get("op")
    if not isinstance(op_raw, str):
        raise ValueError("wiki mutation requires an op field")
    op = _normalize_mutation_op(op_raw)
    if op == "create_synthesis":
        title_value = normalize_optional_string(raw_params.get("title"))
        if not title_value:
            raise ValueError("wiki mutation requires title for create_synthesis.")
        body_value = normalize_optional_string(raw_params.get("body"))
        if not body_value:
            raise ValueError("wiki mutation requires body for create_synthesis.")
        source_ids_value = raw_params.get("sourceIds")
        if not isinstance(source_ids_value, list) or len(source_ids_value) == 0:
            raise ValueError("wiki mutation requires at least one sourceId for create_synthesis.")
        confidence = _normalize_mutation_confidence(raw_params, allow_null=False)
        claims_value = raw_params.get("claims")
        claims_list = list(claims_value) if isinstance(claims_value, list) else []
        return CreateSynthesisMutation(
            title=title_value,
            body=body_value,
            source_ids=source_ids_value,
            claims=claims_list,
            contradictions=normalize_string_entries(raw_params.get("contradictions")),
            questions=normalize_string_entries(raw_params.get("questions")),
            confidence=confidence,
            status=normalize_optional_string(raw_params.get("status")),
        )
    if op == "update_metadata":
        lookup_value = normalize_optional_string(raw_params.get("lookup"))
        if not lookup_value:
            raise ValueError("wiki mutation requires lookup for update_metadata.")
        source_ids_value = raw_params.get("sourceIds")
        source_ids_list = list(source_ids_value) if isinstance(source_ids_value, list) else None
        claims_value = raw_params.get("claims")
        claims_list = list(claims_value) if isinstance(claims_value, list) else None
        contradictions_value = raw_params.get("contradictions")
        contradictions_list = (
            list(contradictions_value) if isinstance(contradictions_value, list) else None
        )
        questions_value = raw_params.get("questions")
        questions_list = list(questions_value) if isinstance(questions_value, list) else None
        # ``_normalize_mutation_confidence``
        # with ``allow_null=True`` returns
        # ``None`` both for "not provided" and
        # for "explicit null". We need to
        # distinguish, so we re-check the raw
        # value here.
        confidence_raw = raw_params.get("confidence", _UNSET)
        if confidence_raw is _UNSET:
            confidence: float | None | Literal["__unset__"] = _UNSET
        elif confidence_raw is None:
            confidence = None
        else:
            confidence = _normalize_mutation_confidence(raw_params, allow_null=True)
        return UpdateMetadataMutation(
            lookup=lookup_value,
            source_ids=source_ids_list,
            claims=claims_list,
            contradictions=contradictions_list,
            questions=questions_list,
            confidence=confidence,
            status=normalize_optional_string(raw_params.get("status")),
        )
    raise ValueError(f"unsupported wiki mutation op: {op_raw!r}")


# ── body builders ─────────────────────────────────────────


def _ensure_human_notes_block(body: str) -> str:
    """Add the ``## Notes`` human-notes block if missing.

    Mirrors the OpenClaw
    ``ensureHumanNotesBlock``. If the body
    already contains both
    :data:`HUMAN_START_MARKER` /
    :data:`HUMAN_END_MARKER`, the body is
    returned unchanged.
    """
    if HUMAN_START_MARKER in body and HUMAN_END_MARKER in body:
        return body
    trimmed = body.rstrip()
    prefix = f"{trimmed}\n\n" if trimmed else ""
    return f"{prefix}## Notes\n{HUMAN_START_MARKER}\n{HUMAN_END_MARKER}\n"


def _build_synthesis_body(
    *,
    title: str,
    original_body: str | None,
    generated_body: str,
) -> str:
    """Build the body for a new synthesis page.

    Mirrors the OpenClaw
    ``buildSynthesisBody``. The body keeps
    the original (operator notes) when
    present; otherwise a fresh
    ``# Title`` + ``## Notes`` block is
    generated. The ``## Summary`` managed
    block is replaced via
    :func:`markdown.replace_managed_markdown_block`.
    """
    if original_body and original_body.strip():
        base = original_body
    else:
        base = f"# {title}\n\n## Notes\n" f"{HUMAN_START_MARKER}\n{HUMAN_END_MARKER}\n"
    with_generated = markdown.replace_managed_markdown_block(
        markdown.ReplaceManagedBlockParams(
            original=base,
            heading="## Summary",
            start_marker=GENERATED_START_MARKER,
            end_marker=GENERATED_END_MARKER,
            body=generated_body,
        )
    )
    return _ensure_human_notes_block(with_generated)


# ── fs-safe page read / write helpers ────────────────────


def _is_missing_wiki_page_error(error: BaseException) -> bool:
    """True iff ``error`` is a ``FsSafeError("not-found")``.

    Mirrors the OpenClaw
    ``isMissingWikiPageError``.
    """
    return isinstance(error, FsSafeError) and error.code == "not-found"


def _read_existing_wiki_page(root: Any, page_path: str) -> str:
    """Read the existing wiki page body.

    Mirrors the OpenClaw
    ``readExistingWikiPage``. Returns an
    empty string when the page doesn't exist
    (so the caller can treat the "create
    synthesis" + "update metadata" paths
    uniformly).
    """
    try:
        return root.read(page_path)
    except Exception as exc:
        if _is_missing_wiki_page_error(exc):
            return ""
        raise


def _write_wiki_page(
    *,
    root_dir: str,
    relative_path: str,
    frontmatter: dict[str, Any],
    body: str,
) -> bool:
    """Render + write a wiki page.

    Mirrors the OpenClaw ``writeWikiPage``.
    Returns ``True`` when the write happened
    (i.e. the rendered content differs from
    the existing content); ``False`` for a
    no-op write.
    """
    root = fs_root(root_dir)
    rendered = markdown.with_trailing_newline(
        render_wiki_markdown(frontmatter=frontmatter, body=body)
    )
    existing = _read_existing_wiki_page(root, relative_path)
    if existing == rendered:
        return False
    root.write(relative_path, rendered)
    return True


# ── mutation handlers ────────────────────────────────────


def _build_updated_frontmatter(  # noqa: PLR0912 — mirrors OpenClaw's per-field branching
    *,
    original: dict[str, Any],
    mutation: UpdateMetadataMutation,
) -> dict[str, Any]:
    """Build the updated frontmatter for an update_metadata mutation.

    Mirrors the OpenClaw
    ``buildUpdatedFrontmatter``. The
    ``updatedAt`` stamp is always refreshed.
    Optional fields are applied when present;
    an empty list / explicit ``None`` for
    ``confidence`` removes the field.
    """
    frontmatter: dict[str, Any] = dict(original)
    # ``updatedAt`` is always refreshed. The
    # OpenClaw source uses ``new Date().toISOString()``;
    # the Python port delegates to the
    # ``time`` module (the same ISO string).
    from .time import resolve_memory_wiki_timestamp

    frontmatter["updatedAt"] = resolve_memory_wiki_timestamp()
    if mutation.source_ids is not None:
        frontmatter["sourceIds"] = normalize_source_ids(mutation.source_ids)
    if mutation.claims is not None:
        claims = normalize_wiki_claims(mutation.claims)
        if claims:
            frontmatter["claims"] = claims
        else:
            frontmatter.pop("claims", None)
    if mutation.contradictions is not None:
        contradictions = unique_strings(normalize_string_entries(mutation.contradictions))
        if contradictions:
            frontmatter["contradictions"] = contradictions
        else:
            frontmatter.pop("contradictions", None)
    if mutation.questions is not None:
        questions = unique_strings(normalize_string_entries(mutation.questions))
        if questions:
            frontmatter["questions"] = questions
        else:
            frontmatter.pop("questions", None)
    if mutation.confidence is _UNSET:
        # ``confidence`` not provided → keep
        # the existing value.
        pass
    elif mutation.confidence is None:
        # Explicit ``null`` → clear the field.
        frontmatter.pop("confidence", None)
    else:
        frontmatter["confidence"] = mutation.confidence
    if mutation.status is not None and mutation.status.strip():
        frontmatter["status"] = mutation.status.strip()
    return frontmatter


def _apply_create_synthesis_mutation(
    *,
    config: ResolvedMemoryWikiConfig,
    mutation: CreateSynthesisMutation,
) -> tuple[bool, str, str]:
    """Apply a create_synthesis mutation. Returns (changed, pagePath, pageId)."""
    slug = slugify_wiki_segment(mutation.title)
    page_stem = slugify_wiki_page_stem(mutation.title)
    page_path = os.path.join("syntheses", f"{page_stem}.md").replace("\\", "/")
    root = fs_root(config.vault.path)
    existing = _read_existing_wiki_page(root, page_path)
    parsed = markdown.parse_wiki_frontmatter(existing) or markdown.ParsedWikiMarkdown(
        has_frontmatter=False, frontmatter={}, body=""
    )
    page_id_raw = parsed.frontmatter.get("id")
    page_id = (
        page_id_raw if isinstance(page_id_raw, str) and page_id_raw.strip() else f"synthesis.{slug}"
    )
    frontmatter: dict[str, Any] = {
        **parsed.frontmatter,
        "pageType": "synthesis",
        "id": page_id,
        "title": mutation.title,
        "sourceIds": normalize_source_ids(mutation.source_ids),
        "status": (mutation.status or "active").strip() or "active",
    }
    if mutation.claims:
        normalized_claims = normalize_wiki_claims(mutation.claims)
        if normalized_claims:
            frontmatter["claims"] = normalized_claims
    if mutation.contradictions:
        normalized_contradictions = unique_strings(
            normalize_string_entries(mutation.contradictions)
        )
        if normalized_contradictions:
            frontmatter["contradictions"] = normalized_contradictions
    if mutation.questions:
        normalized_questions = unique_strings(normalize_string_entries(mutation.questions))
        if normalized_questions:
            frontmatter["questions"] = normalized_questions
    if isinstance(mutation.confidence, int | float):
        frontmatter["confidence"] = mutation.confidence
    from .time import resolve_memory_wiki_timestamp

    frontmatter["updatedAt"] = resolve_memory_wiki_timestamp()
    body = _build_synthesis_body(
        title=mutation.title,
        original_body=parsed.body,
        generated_body=mutation.body.strip(),
    )
    changed = _write_wiki_page(
        root_dir=config.vault.path,
        relative_path=page_path,
        frontmatter=frontmatter,
        body=body,
    )
    return changed, page_path, page_id


def _apply_update_metadata_mutation(
    *,
    config: ResolvedMemoryWikiConfig,
    mutation: UpdateMetadataMutation,
) -> tuple[bool, str, str | None]:
    """Apply an update_metadata mutation. Returns (changed, pagePath, pageId?)."""
    pages = read_queryable_wiki_pages(config.vault.path)
    page = resolve_queryable_wiki_page_by_lookup(pages, mutation.lookup)
    if page is None:
        raise ValueError(f"Wiki page not found: {mutation.lookup}")
    parsed = markdown.parse_wiki_frontmatter(page.raw) or markdown.ParsedWikiMarkdown(
        has_frontmatter=False, frontmatter={}, body=""
    )
    frontmatter = _build_updated_frontmatter(original=parsed.frontmatter, mutation=mutation)
    changed = _write_wiki_page(
        root_dir=config.vault.path,
        relative_path=page.page.relative_path,
        frontmatter=frontmatter,
        body=parsed.body,
    )
    return changed, page.page.relative_path, page.page.id


def apply_memory_wiki_mutation(
    *,
    config: ResolvedMemoryWikiConfig,
    mutation: ApplyMutation,
) -> ApplyMutationResult:
    """Apply a memory-wiki mutation.

    Mirrors the OpenClaw
    ``applyMemoryWikiMutation``. Wraps the
    write in
    :func:`with_memory_wiki_vault_mutation`
    so concurrent compile / apply calls on
    the same vault serialize. After a
    successful write, the compile pipeline
    is re-run so the compiled cache +
    dashboards reflect the new state.

    The function is sync (the rest of the
    compile pipeline is sync); the per-vault
    async lock inside ``mutation_coordinator``
    is driven via ``asyncio.run`` (matching
    the sync compile_pages pattern).
    """
    import asyncio

    async def _mutation() -> ApplyMutationResult:
        initialize_memory_wiki_vault(config)
        if mutation.op == "create_synthesis":
            changed, page_path, page_id = _apply_create_synthesis_mutation(
                config=config,
                mutation=mutation,
            )
        else:
            changed, page_path, page_id = _apply_update_metadata_mutation(
                config=config,
                mutation=mutation,
            )
        compile_result = compile_wiki_vault(config)
        return ApplyMutationResult(
            changed=changed,
            operation=mutation.op,
            page_path=page_path,
            page_id=page_id,
            scanned_count=compile_result.scanned_count,
            invalid_count=compile_result.invalid_count,
            ignored_count=compile_result.ignored_count,
        )

    return asyncio.run(with_memory_wiki_vault_mutation(config.vault.path, _mutation))


def reset_memory_wiki_apply_state_for_tests() -> None:
    """Reset module-level state (test-only helper).

    The apply path is stateless; this helper
    exists so test code can call a known
    name (mirroring the OpenClaw
    ``resetMemoryWikiApplyStateForTests``
    pattern used by other modules).
    """
    return


__all__ = [
    "ApplyMutation",
    "ApplyMutationResult",
    "CreateSynthesisMutation",
    "GENERATED_END_MARKER",
    "GENERATED_START_MARKER",
    "HUMAN_END_MARKER",
    "HUMAN_START_MARKER",
    "MutationInputOp",
    "MutationOp",
    "UpdateMetadataMutation",
    "apply_memory_wiki_mutation",
    "normalize_memory_wiki_mutation_input",
    "reset_memory_wiki_apply_state_for_tests",
]
