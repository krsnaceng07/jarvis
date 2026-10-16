"""lint — Memory Wiki vault lint (Phase 4.3g-mr1 deep port).

OpenClaw parity: mirrors
``extensions/memory-wiki/src/lint.ts``.

The lint checker walks every compiled
wiki page + the frontmatter errors and
emits a single :class:`WikiLintResult`
with a categorized issue list. The
host consumes this from the
``wiki.lint`` gateway method and from
the ``wiki lint`` CLI command.

Categories (mirrors OpenClaw):

- ``structure`` — missing id / page type
  / title, duplicate id, invalid
  frontmatter
- ``provenance`` — missing ``sourceIds``,
  missing import provenance
- ``links`` — broken wikilinks
- ``contradictions`` — claim
  contradiction clusters
- ``open-questions`` — pages listing
  open questions
- ``quality`` — low-confidence pages /
  claims, stale pages / claims, missing
  claim evidence

The result is also written to
``<vault>/reports/lint.md`` as a
managed ``## Generated`` block, and the
lint event is appended to the vault log.
"""

# ruff: noqa: N815, PLR0912, PLR0915, ASYNC230, UP038 — field names mirror the
# OpenClaw camelCase JSON shape so the
# ``wiki.lint`` gateway response is
# byte-compatible with the OpenClaw host;
# the per-page issue collector mirrors
# OpenClaw's exhaustive branch ladder
# (intentionally long); the report writer
# uses sync ``open`` inside an async
# function (file is small, the lint is
# already a heavy operation).

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from .claim_health import (
    assess_page_freshness,
    build_claim_contradiction_clusters,
    collect_wiki_claim_health,
)
from .compile_pipeline import compile_wiki_vault
from .log import append_memory_wiki_log
from .markdown import (
    ReplaceManagedBlockParams,
    parse_wiki_frontmatter,
    replace_managed_markdown_block,
    with_trailing_newline,
)
from .markdown_pages import render_wiki_markdown, slugify_wiki_segment
from .source_sync_state import read_memory_wiki_source_sync_state

if TYPE_CHECKING:
    from .config import ResolvedMemoryWikiConfig


# Mirrors the OpenClaw
# ``MemoryWikiLintIssue["category"]`` union.
LINT_ISSUE_CATEGORIES: tuple[str, ...] = (
    "structure",
    "provenance",
    "links",
    "contradictions",
    "open-questions",
    "quality",
)

# Mirrors the OpenClaw
# ``MemoryWikiLintIssue["code"]`` union.
LINT_ISSUE_CODES: tuple[str, ...] = (
    "invalid-frontmatter",
    "missing-id",
    "duplicate-id",
    "missing-page-type",
    "page-type-mismatch",
    "missing-title",
    "missing-source-ids",
    "missing-import-provenance",
    "broken-wikilink",
    "contradiction-present",
    "claim-conflict",
    "open-question",
    "low-confidence",
    "claim-low-confidence",
    "claim-missing-evidence",
    "stale-page",
    "stale-claim",
)


@dataclass(frozen=True, slots=True)
class WikiLintIssue:
    """A single vault lint issue.

    Mirrors the OpenClaw
    ``MemoryWikiLintIssue`` type. All
    field names are camelCase so the
    ``wiki.lint`` gateway response is
    byte-compatible with the OpenClaw host.
    """

    severity: str  # "error" | "warning"
    category: str
    code: str
    path: str
    message: str


@dataclass(frozen=True, slots=True)
class WikiLintResult:
    """The result of :func:`lint_memory_wiki_vault`.

    Mirrors the OpenClaw
    ``LintMemoryWikiResult`` type. The
    field names are camelCase so the
    ``wiki.lint`` gateway response is
    byte-compatible with the OpenClaw host.
    """

    vaultRoot: str
    issueCount: int
    issues: list[WikiLintIssue]
    issuesByCategory: dict[str, list[WikiLintIssue]]
    reportPath: str


# ── Helpers ──────────────────────────────────────────────────


def _is_unmanaged_raw_source_page(
    page: Any,
    managed_imported_source_page_paths: set[str],
) -> bool:
    """Return True iff ``page`` is an unmanaged raw source.

    Mirrors the OpenClaw
    ``isUnmanagedRawSourcePage`` helper.
    """
    unmanaged = _read_attr(page, "unmanaged_raw_source_body", "unmanagedRawSourceBody")
    if not unmanaged:
        return False
    relative = _read_attr(page, "relative_path", "relativePath")
    return isinstance(relative, str) and relative not in managed_imported_source_page_paths


def _read_attr(value: Any, *names: str) -> Any:
    """Read the first present attribute from ``value`` among ``names``."""
    for name in names:
        if hasattr(value, name):
            return getattr(value, name)
    return None


def _normalize_lint_target(value: str, *, strip_query: bool) -> str:
    """Normalize a wiki-link target.

    Mirrors the OpenClaw
    ``normalizeLintTarget`` helper.
    """
    without_fragment = value.strip().replace("\\", "/").split("#", 1)[0] or ""
    target = without_fragment.split("?", 1)[0] if strip_query else without_fragment
    return target.replace(".md", "").replace(".MD", "").lstrip("./").lstrip("/").rstrip("/").strip()


def _normalize_lint_path_target(value: str) -> str:
    return _normalize_lint_target(value, strip_query=True)


def _normalize_lint_alias_text_target(value: str) -> str:
    return _normalize_lint_target(value, strip_query=False)


def _normalize_lint_alias_target(value: str) -> str:
    text = _normalize_lint_alias_text_target(value)
    return text.lower() if text else ""


def _has_lint_target_query(value: str) -> bool:
    without_fragment = value.strip().replace("\\", "/").split("#", 1)[0] or ""
    return "?" in without_fragment


def _is_lint_path_style_target(value: str) -> bool:
    without_fragment = value.strip().replace("\\", "/").split("#", 1)[0] or ""
    without_query = without_fragment.split("?", 1)[0] or ""
    return (
        without_query.startswith(("/", "./"))
        or "/" in without_query
        or without_query.lower().endswith(".md")
    )


def _add_path_target(index: dict[str, set[str]], raw: str | None) -> None:
    normalized = _normalize_lint_path_target(raw) if raw else ""
    if not normalized:
        return
    index["pathTargets"].add(normalized)
    base = os.path.basename(normalized.replace("/", os.sep))
    index["pathTargets"].add(base)


def _add_alias_target(index: dict[str, set[str]], raw: str | None) -> None:
    normalized = _normalize_lint_alias_target(raw) if raw else ""
    if normalized:
        index["aliasTargets"].add(normalized)


def _add_slug_alias_target(index: dict[str, set[str]], raw: str | None) -> None:
    if not raw:
        return
    text = _normalize_lint_alias_text_target(raw)
    if text:
        index["aliasTargets"].add(slugify_wiki_segment(text))


def _add_title_target(index: dict[str, set[str]], raw: str | None) -> None:
    _add_alias_target(index, raw)
    _add_slug_alias_target(index, raw)


def _add_path_suffix_targets(index: dict[str, set[str]], raw: str | None) -> None:
    normalized = _normalize_lint_path_target(raw) if raw else ""
    if not normalized:
        return
    parts = [p for p in normalized.split("/") if p]
    for i in range(len(parts)):
        suffix = "/".join(parts[i:])
        _add_path_target(index, suffix)
        _add_slug_alias_target(index, suffix)


def _build_wiki_link_target_index(pages: list[Any]) -> dict[str, set[str]]:
    index: dict[str, set[str]] = {"pathTargets": set(), "aliasTargets": set()}
    for page in pages:
        relative = _read_attr(page, "relative_path", "relativePath")
        title = _read_attr(page, "title")
        _add_path_target(index, relative if isinstance(relative, str) else None)
        _add_title_target(index, title if isinstance(title, str) else None)
        for attr in (
            "source_path",
            "sourcePath",
            "bridge_relative_path",
            "bridgeRelativePath",
            "unsafe_local_relative_path",
            "unsafeLocalRelativePath",
        ):
            value = _read_attr(page, attr)
            if isinstance(value, str):
                _add_path_suffix_targets(index, value)
    return index


def _has_valid_wiki_link_target(index: dict[str, set[str]], raw_target: str) -> bool:
    path_target = _normalize_lint_path_target(raw_target)
    if not path_target:
        return True
    if path_target in index["pathTargets"] and (
        not _has_lint_target_query(raw_target) or _is_lint_path_style_target(raw_target)
    ):
        return True
    if "/" in path_target:
        return False
    return (
        _normalize_lint_alias_target(raw_target) in index["aliasTargets"]
        or slugify_wiki_segment(_normalize_lint_alias_text_target(raw_target))
        in index["aliasTargets"]
    )


def _collect_broken_link_issues(pages: list[Any]) -> list[WikiLintIssue]:
    """Return broken-link lint issues for ``pages``.

    Mirrors the OpenClaw
    ``collectBrokenLinkIssues`` helper.
    """
    valid_targets = _build_wiki_link_target_index(pages)
    issues: list[WikiLintIssue] = []
    for page in pages:
        relative = _read_attr(page, "relative_path", "relativePath")
        if not isinstance(relative, str):
            continue
        link_targets = _read_attr(page, "link_targets", "linkTargets") or []
        for raw_target in link_targets:
            if not isinstance(raw_target, str):
                continue
            if _has_valid_wiki_link_target(valid_targets, raw_target):
                continue
            issues.append(
                WikiLintIssue(
                    severity="warning",
                    category="links",
                    code="broken-wikilink",
                    path=relative,
                    message=f"Wiki link `{raw_target}` does not resolve to a known page or alias.",
                )
            )
    return issues


# ── Page-level issues ───────────────────────────────────────


def _to_expected_page_type(page: Any) -> str:
    return str(_read_attr(page, "kind") or "")


def _collect_page_issues(
    pages: list[Any],
    managed_imported_source_page_paths: set[str],
) -> list[WikiLintIssue]:
    """Collect every per-page lint issue.

    Mirrors the OpenClaw ``collectPageIssues``
    helper.
    """
    issues: list[WikiLintIssue] = []
    pages_by_id: dict[str, list[Any]] = {}
    claim_health = collect_wiki_claim_health(pages)

    for page in pages:
        relative = _read_attr(page, "relative_path", "relativePath") or ""
        requires_structured = not _is_unmanaged_raw_source_page(
            page, managed_imported_source_page_paths
        )
        page_id = _read_attr(page, "id")
        page_type = _read_attr(page, "page_type", "pageType")
        title = _read_attr(page, "title") or ""
        kind = _read_attr(page, "kind") or ""
        source_ids = _read_attr(page, "source_ids", "sourceIds") or []
        source_type = _read_attr(page, "source_type", "sourceType")
        provenance_mode = _read_attr(page, "provenance_mode", "provenanceMode")
        source_path = _read_attr(page, "source_path", "sourcePath")
        bridge_relative = _read_attr(page, "bridge_relative_path", "bridgeRelativePath")
        bridge_workspace = _read_attr(page, "bridge_workspace_dir", "bridgeWorkspaceDir")
        unsafe_local_configured = _read_attr(
            page, "unsafe_local_configured_path", "unsafeLocalConfiguredPath"
        )
        unsafe_local_relative = _read_attr(
            page, "unsafe_local_relative_path", "unsafeLocalRelativePath"
        )
        contradictions = _read_attr(page, "contradictions") or []
        questions = _read_attr(page, "questions") or []
        confidence = _read_attr(page, "confidence")

        if not page_id:
            if requires_structured:
                issues.append(
                    WikiLintIssue(
                        severity="error",
                        category="structure",
                        code="missing-id",
                        path=relative,
                        message="Missing `id` frontmatter.",
                    )
                )
        else:
            pages_by_id.setdefault(str(page_id), []).append(page)

        if not page_type:
            if requires_structured:
                issues.append(
                    WikiLintIssue(
                        severity="error",
                        category="structure",
                        code="missing-page-type",
                        path=relative,
                        message="Missing `pageType` frontmatter.",
                    )
                )
        elif page_type != _to_expected_page_type(page):
            issues.append(
                WikiLintIssue(
                    severity="error",
                    category="structure",
                    code="page-type-mismatch",
                    path=relative,
                    message=(
                        f"Expected pageType `{_to_expected_page_type(page)}`, found `{page_type}`."
                    ),
                )
            )

        if not str(title).strip():
            issues.append(
                WikiLintIssue(
                    severity="error",
                    category="structure",
                    code="missing-title",
                    path=relative,
                    message="Missing page title.",
                )
            )

        if kind not in ("source", "report") and len(source_ids) == 0:
            issues.append(
                WikiLintIssue(
                    severity="warning",
                    category="provenance",
                    code="missing-source-ids",
                    path=relative,
                    message="Non-source page is missing `sourceIds` provenance.",
                )
            )

        if (source_type in ("memory-bridge", "memory-bridge-events")) and (
            not source_path or not bridge_relative or not bridge_workspace
        ):
            issues.append(
                WikiLintIssue(
                    severity="warning",
                    category="provenance",
                    code="missing-import-provenance",
                    path=relative,
                    message=(
                        "Bridge-imported source page is missing `sourcePath`, "
                        "`bridgeRelativePath`, or `bridgeWorkspaceDir` provenance."
                    ),
                )
            )

        if (provenance_mode == "unsafe-local" or source_type == "memory-unsafe-local") and (
            not source_path or not unsafe_local_configured or not unsafe_local_relative
        ):
            issues.append(
                WikiLintIssue(
                    severity="warning",
                    category="provenance",
                    code="missing-import-provenance",
                    path=relative,
                    message=(
                        "Unsafe-local source page is missing `sourcePath`, "
                        "`unsafeLocalConfiguredPath`, or `unsafeLocalRelativePath` provenance."
                    ),
                )
            )

        if len(contradictions) > 0:
            issues.append(
                WikiLintIssue(
                    severity="warning",
                    category="contradictions",
                    code="contradiction-present",
                    path=relative,
                    message=(
                        f"Page lists {len(contradictions)} contradiction"
                        f"{'' if len(contradictions) == 1 else 's'} to resolve."
                    ),
                )
            )

        if len(questions) > 0:
            issues.append(
                WikiLintIssue(
                    severity="warning",
                    category="open-questions",
                    code="open-question",
                    path=relative,
                    message=(
                        f"Page lists {len(questions)} open question"
                        f"{'' if len(questions) == 1 else 's'}."
                    ),
                )
            )

        if isinstance(confidence, (int, float)) and float(confidence) < 0.5:
            issues.append(
                WikiLintIssue(
                    severity="warning",
                    category="quality",
                    code="low-confidence",
                    path=relative,
                    message=f"Page confidence is low ({float(confidence):.2f}).",
                )
            )

        freshness = assess_page_freshness(page)
        freshness_level = str(freshness.level) if freshness else ""
        freshness_reason = str(freshness.reason) if freshness else ""
        if requires_structured and kind != "report" and freshness_level in ("stale", "unknown"):
            issues.append(
                WikiLintIssue(
                    severity="warning",
                    category="quality",
                    code="stale-page",
                    path=relative,
                    message=f"Page freshness needs review ({freshness_reason}).",
                )
            )

    for claim in claim_health:
        claim_path = _read_attr(claim, "page_path", "pagePath") or ""
        claim_id = _read_attr(claim, "claim_id", "claimId")
        claim_text = _read_attr(claim, "text") or ""
        claim_label = f"`{claim_id}`" if claim_id else f"`{claim_text}`"
        if _read_attr(claim, "missing_evidence", "missingEvidence"):
            issues.append(
                WikiLintIssue(
                    severity="warning",
                    category="provenance",
                    code="claim-missing-evidence",
                    path=claim_path,
                    message=f"Claim {claim_label} is missing structured evidence.",
                )
            )
        confidence = _read_attr(claim, "confidence")
        if isinstance(confidence, (int, float)) and float(confidence) < 0.5:
            issues.append(
                WikiLintIssue(
                    severity="warning",
                    category="quality",
                    code="claim-low-confidence",
                    path=claim_path,
                    message=(f"Claim {claim_label} has low confidence ({float(confidence):.2f})."),
                )
            )
        claim_freshness = _read_attr(claim, "freshness")
        claim_freshness_level = (
            str(_read_attr(claim_freshness, "level") or "") if claim_freshness is not None else ""
        )
        claim_freshness_reason = (
            str(_read_attr(claim_freshness, "reason") or "") if claim_freshness is not None else ""
        )
        if claim_freshness_level in ("stale", "unknown"):
            issues.append(
                WikiLintIssue(
                    severity="warning",
                    category="quality",
                    code="stale-claim",
                    path=claim_path,
                    message=(
                        f"Claim {claim_label} freshness needs review ({claim_freshness_reason})."
                    ),
                )
            )

    for cluster in build_claim_contradiction_clusters(pages=pages):
        cluster_label = _read_attr(cluster, "label") or ""
        entries = _read_attr(cluster, "entries") or []
        for entry in entries:
            entry_path = _read_attr(entry, "page_path", "pagePath") or ""
            issues.append(
                WikiLintIssue(
                    severity="warning",
                    category="contradictions",
                    code="claim-conflict",
                    path=entry_path,
                    message=(
                        f"Claim cluster `{cluster_label}` has competing variants "
                        f"across {len(entries)} pages."
                    ),
                )
            )

    for pid, matches in pages_by_id.items():
        if len(matches) > 1:
            for match in matches:
                match_path = _read_attr(match, "relative_path", "relativePath") or ""
                issues.append(
                    WikiLintIssue(
                        severity="error",
                        category="structure",
                        code="duplicate-id",
                        path=match_path,
                        message=f"Duplicate page id `{pid}`.",
                    )
                )

    issues.extend(_collect_broken_link_issues(pages))
    issues.sort(key=lambda i: i.path)
    return issues


def _build_issues_by_category(
    issues: list[WikiLintIssue],
) -> dict[str, list[WikiLintIssue]]:
    """Group issues by category.

    Mirrors the OpenClaw
    ``buildIssuesByCategory`` helper.
    Every category is always present in
    the result (empty list when there are
    no issues for that category).
    """
    by_category = {category: [] for category in LINT_ISSUE_CATEGORIES}
    for issue in issues:
        if issue.category in by_category:
            by_category[issue.category].append(issue)
    return by_category


def _build_lint_report_body(issues: list[WikiLintIssue]) -> str:
    """Build the body of the ``reports/lint.md`` file.

    Mirrors the OpenClaw
    ``buildLintReportBody`` helper.
    """
    if not issues:
        return "No issues found."
    errors = [i for i in issues if i.severity == "error"]
    warnings = [i for i in issues if i.severity == "warning"]
    by_category = _build_issues_by_category(issues)
    lines = [f"- Errors: {len(errors)}", f"- Warnings: {len(warnings)}"]
    if errors:
        lines.append("")
        lines.append("### Errors")
        for issue in errors:
            lines.append(f"- `{issue.path}`: {issue.message}")
    if warnings:
        lines.append("")
        lines.append("### Warnings")
        for issue in warnings:
            lines.append(f"- `{issue.path}`: {issue.message}")
    if by_category["contradictions"]:
        lines.append("")
        lines.append("### Contradictions")
        for issue in by_category["contradictions"]:
            lines.append(f"- `{issue.path}`: {issue.message}")
    if by_category["open-questions"]:
        lines.append("")
        lines.append("### Open Questions")
        for issue in by_category["open-questions"]:
            lines.append(f"- `{issue.path}`: {issue.message}")
    if by_category["provenance"] or by_category["quality"]:
        lines.append("")
        lines.append("### Quality Follow-Up")
        for issue in by_category["provenance"] + by_category["quality"]:
            lines.append(f"- `{issue.path}`: {issue.message}")
    return "\n".join(lines)


async def _write_lint_report(root_dir: str, issues: list[WikiLintIssue]) -> str:
    """Write the ``reports/lint.md`` file with the issue list.

    Mirrors the OpenClaw ``writeLintReport``
    helper. The report is itself a wiki
    page; the issue list lives inside a
    managed ``## Generated`` block so the
    page's metadata survives re-runs.
    """
    report_path = os.path.join(root_dir, "reports", "lint.md")
    default_body = render_wiki_markdown(
        frontmatter={
            "pageType": "report",
            "id": "report.lint",
            "title": "Lint Report",
            "status": "active",
        },
        body="# Lint Report\n",
    )
    try:
        with open(report_path, encoding="utf-8") as f:
            original = f.read()
    except OSError:
        original = default_body
    # Fail-closed on malformed frontmatter:
    # if the existing file has un-parseable
    # frontmatter, do NOT rewrite it. Just
    # leave the issue list unreported.
    parse_wiki_frontmatter(original)
    updated = replace_managed_markdown_block(
        ReplaceManagedBlockParams(
            original=original,
            heading="## Generated",
            start_marker="<!-- openclaw:wiki:lint:start -->",
            end_marker="<!-- openclaw:wiki:lint:end -->",
            body=_build_lint_report_body(issues),
        )
    )
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(with_trailing_newline(updated))
    return report_path


# ── Public API ──────────────────────────────────────────────


async def lint_memory_wiki_vault(
    config: ResolvedMemoryWikiConfig,
) -> WikiLintResult:
    """Lint the wiki vault.

    Mirrors the OpenClaw
    :func:`lintMemoryWikiVault`. Returns
    a categorized issue list + writes
    ``<vault>/reports/lint.md`` + appends
    a ``lint`` log entry.
    """
    compile_result = compile_wiki_vault(config)
    source_sync_state = read_memory_wiki_source_sync_state(config.vault.path)
    managed_paths = {
        str(entry.page_path).replace(os.sep, "/") for entry in source_sync_state.entries.values()
    }
    fm_errors = [
        WikiLintIssue(
            severity="error",
            category="structure",
            code="invalid-frontmatter",
            path=error.relative_path,
            message=f"Frontmatter failed to parse: {error.message}",
        )
        for error in compile_result.invalid_paths
    ]
    page_issues = _collect_page_issues(compile_result.pages, managed_paths)
    all_issues = fm_errors + page_issues
    all_issues.sort(key=lambda i: i.path)
    issues_by_category = _build_issues_by_category(all_issues)
    report_path = await _write_lint_report(config.vault.path, all_issues)
    append_memory_wiki_log(
        config.vault.path,
        {
            "type": "lint",
            "details": {
                "issueCount": len(all_issues),
                "reportPath": os.path.relpath(report_path, config.vault.path),
            },
        },
    )
    return WikiLintResult(
        vaultRoot=config.vault.path,
        issueCount=len(all_issues),
        issues=all_issues,
        issuesByCategory=issues_by_category,
        reportPath=report_path,
    )


def reset_memory_wiki_lint_state_for_tests() -> None:
    """Reset module-level state (test-only helper)."""
    return


__all__ = [
    "LINT_ISSUE_CATEGORIES",
    "LINT_ISSUE_CODES",
    "WikiLintIssue",
    "WikiLintResult",
    "lint_memory_wiki_vault",
    "reset_memory_wiki_lint_state_for_tests",
]
