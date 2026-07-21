"""compile_render — memory-wiki dashboard rendering.

OpenClaw parity: ports the
``DASHBOARD_PAGES`` block from
``extensions/memory-wiki/src/compile.ts``.

Phase 4.3d-mr5 ships the body builders for the
5 core dashboards:
- ``report.open-questions`` -- pages with open
  questions.
- ``report.contradictions`` -- page-note + claim
  contradiction clusters.
- ``report.low-confidence`` -- pages / claims
  with ``confidence < 0.5``.
- ``report.claim-health`` -- missing-evidence /
  contested / stale-or-unknown claims.
- ``report.stale-pages`` -- pages with
  ``freshness.level != "fresh"`` (excluding
  concept / synthesis kinds + unmanaged raw
  sources).

Each dashboard exposes a ``build_body`` function
that takes the page summaries + the
:func:`extensions.memory_wiki.config.ResolvedMemoryWikiConfig`
and returns a markdown string. The
``render_wiki_dashboards`` orchestrator builds
all 5 and returns a list of
:class:`DashboardBuild` results ready to be
written to disk (the disk-write step lives in
4.3d-mr6 / 4.3e).

Person-directory, relationship-graph, and
provenance-coverage dashboards ship as follow-up
work in 4.3f (they depend on person-card
normalization + the bridge mode runtime which
isn't in the 4.3d scope).
"""

from __future__ import annotations

import posixpath
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

from .claim_health import (
    WIKI_AGING_DAYS,
    WikiClaimContradictionCluster,
    WikiPageContradictionCluster,
    _read_attr,
    assess_page_freshness,
    build_claim_contradiction_clusters,
    build_page_contradiction_clusters,
    collect_wiki_claim_health,
    is_claim_contested_status,
    normalize_claim_status,
)
from .wiki_page_summary import WikiPageSummary  # noqa: TCH001  -- runtime + type use

if TYPE_CHECKING:
    from .config import ResolvedMemoryWikiConfig


# ── Link formatter ──────────────────────────────────────────


def format_wiki_link(
    *,
    render_mode: str,
    relative_path: str,
    source_relative_to: str,
    title: str,
) -> str:
    """Format a wiki link in native or Obsidian style.

    Mirrors OpenClaw's ``formatWikiLink``. The
    Obsidian form is ``[[target|title]]``; the
    native form is ``[title](relative-url)``.
    """
    without_extension = re_sub_ext(relative_path)
    if render_mode == "obsidian":
        return f"[[{without_extension}|{title}]]"
    if source_relative_to:
        # Compute the POSIX-relative path from
        # ``source_relative_to`` to
        # ``relative_path``.
        source_dir = posixpath.dirname(source_relative_to)
        if source_dir and source_dir != ".":
            link_target = posixpath.relpath(relative_path, source_dir)
        else:
            link_target = relative_path
    else:
        link_target = relative_path
    return f"[{title}]({link_target})"


def re_sub_ext(relative_path: str) -> str:
    """Drop a trailing ``.md`` (case-insensitive).

    Mirrors OpenClaw's inline ``withoutExtension``
    pattern in ``formatWikiLink``.
    """
    if relative_path.lower().endswith(".md"):
        return relative_path[:-3]
    return relative_path


# ── Dashboard body builders ─────────────────────────────────


def build_open_questions_body(
    *,
    config: ResolvedMemoryWikiConfig,
    pages: list[WikiPageSummary],
    source_relative_to: str,
) -> str:
    """Build the body of the ``reports/open-questions.md`` dashboard.

    Mirrors the OpenClaw
    ``report.open-questions.buildBody``.
    """
    matches = [page for page in pages if len(_read_attr(page, "questions") or []) > 0]
    if not matches:
        return "- No open questions right now."
    lines = [f"- Pages with open questions: {len(matches)}", ""]
    for page in matches:
        link = format_wiki_link(
            render_mode=config.vault.renderMode,
            relative_path=_read_attr(page, "relativePath", "relative_path") or "",
            source_relative_to=source_relative_to,
            title=_read_attr(page, "title") or "",
        )
        questions = " | ".join(_read_attr(page, "questions") or [])
        lines.append(f"- {link}: {questions}")
    return "\n".join(lines)


def build_contradictions_body(
    *,
    config: ResolvedMemoryWikiConfig,
    pages: list[WikiPageSummary],
    now: datetime,
    source_relative_to: str,
) -> str:
    """Build the body of the ``reports/contradictions.md`` dashboard.

    Mirrors the OpenClaw
    ``report.contradictions.buildBody``.
    """
    page_clusters = build_page_contradiction_clusters(pages)
    claim_clusters = build_claim_contradiction_clusters(pages=pages, now=now)
    if not page_clusters and not claim_clusters:
        return "- No contradictions flagged right now."
    lines = [
        f"- Contradiction note clusters: {len(page_clusters)}",
        f"- Competing claim clusters: {len(claim_clusters)}",
    ]
    if page_clusters:
        lines.append("")
        lines.append("### Page Notes")
        for cluster in page_clusters:
            lines.append(
                _format_page_cluster_line(
                    config=config,
                    cluster=cluster,
                    source_relative_to=source_relative_to,
                )
            )
    if claim_clusters:
        lines.append("")
        lines.append("### Claim Clusters")
        for cluster in claim_clusters:
            lines.append(
                _format_claim_cluster_line(
                    config=config,
                    cluster=cluster,
                    source_relative_to=source_relative_to,
                )
            )
    return "\n".join(lines)


def build_low_confidence_body(
    *,
    config: ResolvedMemoryWikiConfig,
    pages: list[WikiPageSummary],
    now: datetime,
    source_relative_to: str,
) -> str:
    """Build the body of the ``reports/low-confidence.md`` dashboard.

    Mirrors the OpenClaw
    ``report.low-confidence.buildBody``.
    """
    page_matches: list[Any] = []
    for page in pages:
        confidence = _read_attr(page, "confidence")
        if isinstance(confidence, int | float) and confidence < 0.5:
            page_matches.append((page, float(confidence)))
    page_matches.sort(key=lambda pair: pair[1])
    claim_matches: list[tuple[Any, float]] = []
    for claim in collect_wiki_claim_health(pages, now):
        confidence = claim.confidence
        if isinstance(confidence, int | float) and confidence < 0.5:
            claim_matches.append((claim, float(confidence)))
    claim_matches.sort(key=lambda pair: pair[1])
    if not page_matches and not claim_matches:
        return "- No low-confidence pages or claims right now."
    lines = [
        f"- Low-confidence pages: {len(page_matches)}",
        f"- Low-confidence claims: {len(claim_matches)}",
    ]
    if page_matches:
        lines.append("")
        lines.append("### Pages")
        for page, confidence in page_matches:
            link = format_wiki_link(
                render_mode=config.vault.renderMode,
                relative_path=_read_attr(page, "relativePath", "relative_path") or "",
                source_relative_to=source_relative_to,
                title=_read_attr(page, "title") or "",
            )
            lines.append(f"- {link}: confidence {confidence:.2f}")
    if claim_matches:
        lines.append("")
        lines.append("### Claims")
        for claim, confidence in claim_matches:
            link = format_wiki_link(
                render_mode=config.vault.renderMode,
                relative_path=claim.page_path,
                source_relative_to=source_relative_to,
                title=claim.page_title,
            )
            text = claim.text or claim.claim_id or "<unnamed>"
            lines.append(f"- {link}: {text} (confidence {confidence:.2f})")
    return "\n".join(lines)


def build_claim_health_body(
    *,
    config: ResolvedMemoryWikiConfig,
    pages: list[WikiPageSummary],
    now: datetime,
    source_relative_to: str,
) -> str:
    """Build the body of the ``reports/claim-health.md`` dashboard.

    Mirrors the OpenClaw
    ``report.claim-health.buildBody``.
    """
    claim_health = collect_wiki_claim_health(pages, now)
    missing_evidence = [c for c in claim_health if c.missing_evidence]
    contested = [c for c in claim_health if is_claim_contested_status(c.status)]
    stale = [c for c in claim_health if c.freshness.level in ("stale", "unknown")]
    if not missing_evidence and not contested and not stale:
        return "- No claim health issues right now."
    lines = [
        f"- Claims missing evidence: {len(missing_evidence)}",
        f"- Contested claims: {len(contested)}",
        f"- Stale or unknown claims: {len(stale)}",
    ]
    if missing_evidence:
        lines.append("")
        lines.append("### Missing Evidence")
        for claim in missing_evidence:
            lines.append(f"- {_format_claim_health_link(config, claim, source_relative_to)}")
    if contested:
        lines.append("")
        lines.append("### Contested Claims")
        for claim in contested:
            lines.append(f"- {_format_claim_health_link(config, claim, source_relative_to)}")
    if stale:
        lines.append("")
        lines.append("### Stale Claims")
        for claim in stale:
            lines.append(f"- {_format_claim_health_link(config, claim, source_relative_to)}")
    return "\n".join(lines)


def build_stale_pages_body(
    *,
    config: ResolvedMemoryWikiConfig,
    pages: list[WikiPageSummary],
    now: datetime,
    source_relative_to: str,
) -> str:
    """Build the body of the ``reports/stale-pages.md`` dashboard.

    Mirrors the OpenClaw
    ``report.stale-pages.buildBody``. Concept /
    synthesis kinds are skipped (intentionally
    durable references); unmanaged raw-source
    bodies are also skipped.
    """
    matches: list[tuple[Any, Any]] = []
    for page in pages:
        kind = _read_attr(page, "kind")
        if kind in ("report", "concept", "synthesis"):
            continue
        unmanaged = _read_attr(page, "unmanagedRawSourceBody", "unmanaged_raw_source_body")
        imported = _read_attr(page, "importedSourceBody", "imported_source_body")
        if unmanaged and not imported:
            continue
        freshness = assess_page_freshness(page, now)
        if freshness.level == "fresh":
            continue
        matches.append((page, freshness))
    matches.sort(key=lambda pair: _read_attr(pair[0], "title") or "")
    if not matches:
        return f"- No aging or stale pages older than {WIKI_AGING_DAYS} days."
    lines = [f"- Stale pages: {len(matches)}", ""]
    for page, freshness in matches:
        link = format_wiki_link(
            render_mode=config.vault.renderMode,
            relative_path=_read_attr(page, "relativePath", "relative_path") or "",
            source_relative_to=source_relative_to,
            title=_read_attr(page, "title") or "",
        )
        lines.append(f"- {link}: {_format_freshness_label(freshness)}")
    return "\n".join(lines)


# ── Internal formatters ────────────────────────────────────


def _format_page_cluster_line(
    *,
    config: ResolvedMemoryWikiConfig,
    cluster: WikiPageContradictionCluster,
    source_relative_to: str,
) -> str:
    """Format one page-contradiction cluster as a markdown bullet line.

    Mirrors the OpenClaw
    ``formatPageContradictionClusterLine``.
    """
    parts: list[str] = []
    for entry in cluster.entries:
        link = format_wiki_link(
            render_mode=config.vault.renderMode,
            relative_path=entry.page_path,
            source_relative_to=source_relative_to,
            title=entry.page_title,
        )
        parts.append(f"  - {link}: {entry.note}")
    return f"- {cluster.label}\n" + "\n".join(parts)


def _format_claim_cluster_line(
    *,
    config: ResolvedMemoryWikiConfig,
    cluster: WikiClaimContradictionCluster,
    source_relative_to: str,
) -> str:
    """Format one claim-contradiction cluster as a markdown bullet line.

    Mirrors the OpenClaw
    ``formatClaimContradictionClusterLine``.
    """
    parts: list[str] = []
    for entry in cluster.entries:
        link = format_wiki_link(
            render_mode=config.vault.renderMode,
            relative_path=entry.page_path,
            source_relative_to=source_relative_to,
            title=entry.page_title,
        )
        text = entry.text or entry.claim_id or "<unnamed>"
        parts.append(f"  - {link}: {text} ({entry.status})")
    return f"- {cluster.label}\n" + "\n".join(parts)


def _format_claim_health_link(
    config: ResolvedMemoryWikiConfig,
    claim: Any,
    source_relative_to: str,
) -> str:
    """Format one claim-health row as a markdown bullet line."""
    link = format_wiki_link(
        render_mode=config.vault.renderMode,
        relative_path=claim.page_path,
        source_relative_to=source_relative_to,
        title=claim.page_title,
    )
    text = claim.text or claim.claim_id or "<unnamed>"
    status = normalize_claim_status(claim.status)
    return f"{link}: {text} ({status})"


def _format_freshness_label(freshness: Any) -> str:
    """Return the OpenClaw-shaped freshness label."""
    level = freshness.level
    if level == "unknown":
        return f"unknown ({freshness.reason})"
    if freshness.days_since_touch is None:
        return level
    return f"{level} ({freshness.days_since_touch}d)"


# ── Dashboard registry + orchestrator ────────────────────────


@dataclass
class DashboardBuild:
    """A single rendered dashboard.

    The orchestrator returns a list of these. The
    write step (4.3d-mr6) iterates the list and
    persists each ``body`` to its
    ``relative_path``.
    """

    id: str
    title: str
    relative_path: str
    body: str


# Dashboard registry. Mirrors the OpenClaw
# ``DASHBOARD_PAGES`` array (5 of the 8 dashboards;
# the person / relationship / provenance dashboards
# ship in 4.3f).
DASHBOARD_BUILDERS: dict[str, dict[str, Any]] = {
    "report.open-questions": {
        "title": "Open Questions",
        "relative_path": "reports/open-questions.md",
        "build": lambda *, config, pages, now, source_relative_to: build_open_questions_body(
            config=config, pages=pages, source_relative_to=source_relative_to
        ),
    },
    "report.contradictions": {
        "title": "Contradictions",
        "relative_path": "reports/contradictions.md",
        "build": lambda *, config, pages, now, source_relative_to: build_contradictions_body(
            config=config, pages=pages, now=now, source_relative_to=source_relative_to
        ),
    },
    "report.low-confidence": {
        "title": "Low Confidence",
        "relative_path": "reports/low-confidence.md",
        "build": lambda *, config, pages, now, source_relative_to: build_low_confidence_body(
            config=config, pages=pages, now=now, source_relative_to=source_relative_to
        ),
    },
    "report.claim-health": {
        "title": "Claim Health",
        "relative_path": "reports/claim-health.md",
        "build": lambda *, config, pages, now, source_relative_to: build_claim_health_body(
            config=config, pages=pages, now=now, source_relative_to=source_relative_to
        ),
    },
    "report.stale-pages": {
        "title": "Stale Pages",
        "relative_path": "reports/stale-pages.md",
        "build": lambda *, config, pages, now, source_relative_to: build_stale_pages_body(
            config=config, pages=pages, now=now, source_relative_to=source_relative_to
        ),
    },
}


def render_wiki_dashboards(
    *,
    config: ResolvedMemoryWikiConfig,
    pages: list[WikiPageSummary],
    now: datetime | None = None,
    source_relative_to: str = "",
    include: list[str] | None = None,
) -> list[DashboardBuild]:
    """Build every registered dashboard body.

    Mirrors the OpenClaw
    ``buildDashboardPages`` orchestrator
    (4.3d-mr5's scope: 5 dashboards). Returns a
    list of :class:`DashboardBuild` ready to be
    persisted by the write step (4.3d-mr6).
    """
    effective_now = now or datetime.now()
    selected = include if include is not None else list(DASHBOARD_BUILDERS)
    builds: list[DashboardBuild] = []
    for dashboard_id in selected:
        entry = DASHBOARD_BUILDERS.get(dashboard_id)
        if entry is None:
            continue
        body = entry["build"](
            config=config,
            pages=pages,
            now=effective_now,
            source_relative_to=source_relative_to,
        )
        builds.append(
            DashboardBuild(
                id=dashboard_id,
                title=str(entry["title"]),
                relative_path=str(entry["relative_path"]),
                body=body,
            )
        )
    return builds


__all__ = [
    "DASHBOARD_BUILDERS",
    "DashboardBuild",
    "build_claim_health_body",
    "build_contradictions_body",
    "build_low_confidence_body",
    "build_open_questions_body",
    "build_stale_pages_body",
    "format_wiki_link",
    "render_wiki_dashboards",
]
