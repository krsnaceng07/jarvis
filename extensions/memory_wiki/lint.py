"""lint — Memory Wiki vault lint (Phase 4.3f-mr3 stub).

OpenClaw parity: mirrors
``extensions/memory-wiki/src/lint.ts``.

The full lint implementation (which scans
every page in the vault + categorizes
issues by ``provenance`` / ``contradictions``
/ ``open-questions`` + writes a Markdown
report to ``.openclaw-wiki/lint.md``) lands
in Phase 4.3g. Phase 4.3f-mr3 ships the
:func:`lint_memory_wiki_vault` stub so the
``wiki_lint`` tool surface is fully wired
(Telegram / Discord / CLI can register the
tool today; the lint result will improve
when 4.3g lands the deep checker).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from .config import ResolvedMemoryWikiConfig


@dataclass
class WikiLintIssue:
    """A single vault lint issue.

    Mirrors the OpenClaw ``WikiLintIssue`` shape.
    """

    severity: str  # "error" | "warning" | "info"
    category: str  # "provenance" | "contradictions" | "open-questions" | "structure"
    page_path: str
    message: str


@dataclass
class WikiLintResult:
    """The result of :func:`lint_memory_wiki_vault`.

    Mirrors the OpenClaw ``WikiLintResult``
    shape (the deep checkers are added in
    4.3g).
    """

    vault_path: str
    issue_count: int = 0
    issues: list[WikiLintIssue] = field(default_factory=list)
    issues_by_category: dict[str, list[WikiLintIssue]] = field(default_factory=dict)
    report_path: str | None = None


def lint_memory_wiki_vault(
    config: ResolvedMemoryWikiConfig,
    *,
    report_path: Path | str | None = None,
) -> WikiLintResult:
    """Lint the wiki vault (Phase 4.3f-mr3 stub).

    Returns an empty ``WikiLintResult`` (no
    issues, no report file). The full
    implementation lands in Phase 4.3g.
    """
    vault_path = str(config.vault.path)
    return WikiLintResult(
        vault_path=vault_path,
        issue_count=0,
        issues=[],
        issues_by_category={},
        report_path=str(report_path) if report_path is not None else None,
    )


def reset_memory_wiki_lint_state_for_tests() -> None:
    """Reset module-level state (test-only helper)."""
    return


__all__ = [
    "WikiLintIssue",
    "WikiLintResult",
    "lint_memory_wiki_vault",
    "reset_memory_wiki_lint_state_for_tests",
]
