"""import_insights — Memory Wiki import insights (Phase 4.3g-mr3 stub).

OpenClaw parity: mirrors
``extensions/memory-wiki/src/import-insights.ts``.

The import-insights pipeline walks
every imported ChatGPT source page,
extracts the per-conversation digest
metadata (status / topic / risk
levels / message counts / preference
+ correction signals), and groups the
insights by topic.

The full port lands in the rest of
Phase 4.3g-mr3. This module ships the
public surface shape + a minimal port
of the heading-section / digest-field
extraction so the gateway layer can be
fully wired.
"""

# ruff: noqa: N815 — field names mirror the
# OpenClaw camelCase JSON shape so the
# ``wiki.importInsights`` gateway
# response is byte-compatible with the
# OpenClaw host.

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

from .query import read_queryable_wiki_pages

if TYPE_CHECKING:
    from .config import ResolvedMemoryWikiConfig


RiskLevel = Literal["low", "medium", "high", "unknown"]
DigestStatus = Literal["available", "withheld"]


@dataclass(frozen=True, slots=True)
class MemoryWikiImportInsightItem:
    """A single import-insight item.

    Mirrors the OpenClaw
    ``MemoryWikiImportInsightItem`` type.
    Field names are camelCase.
    """

    pagePath: str
    title: str
    riskLevel: RiskLevel
    riskReasons: list[str]
    labels: list[str]
    topicKey: str
    topicLabel: str
    digestStatus: DigestStatus
    activeBranchMessages: int
    userMessageCount: int
    assistantMessageCount: int
    summary: str
    candidateSignals: list[str] = field(default_factory=list)
    correctionSignals: list[str] = field(default_factory=list)
    preferenceSignals: list[str] = field(default_factory=list)
    firstUserLine: str | None = None
    lastUserLine: str | None = None
    assistantOpener: str | None = None
    createdAt: str | None = None
    updatedAt: str | None = None


@dataclass(frozen=True, slots=True)
class MemoryWikiImportInsightCluster:
    """A per-topic cluster of import insights.

    Mirrors the OpenClaw
    ``MemoryWikiImportInsightCluster`` type.
    """

    key: str
    label: str
    itemCount: int
    highRiskCount: int
    withheldCount: int
    preferenceSignalCount: int
    items: list[MemoryWikiImportInsightItem]
    updatedAt: str | None = None


@dataclass(frozen=True, slots=True)
class MemoryWikiImportInsightsStatus:
    """The result of :func:`list_memory_wiki_import_insights`.

    Mirrors the OpenClaw
    ``MemoryWikiImportInsightsStatus`` type.
    """

    sourceType: str
    totalItems: int
    totalClusters: int
    clusters: list[MemoryWikiImportInsightCluster]


def _extract_heading_section(body: str, heading: str) -> list[str]:
    """Return the lines under ``## {heading}``
    in ``body`` (until the next ``##``
    section).

    Mirrors the OpenClaw
    ``extractHeadingSection`` helper.
    """
    lines = body.splitlines()
    heading_line = f"## {heading}"
    try:
        start = next(i for i, line in enumerate(lines) if line.strip() == heading_line)
    except StopIteration:
        return []
    out: list[str] = []
    for line in lines[start + 1 :]:
        if line.startswith("## "):
            break
        if line.strip():
            out.append(line.rstrip())
    return out


def _extract_digest_field(lines: list[str], prefix: str) -> str | None:
    """Return the value of the ``- {prefix}:`` line
    in ``lines``.

    Mirrors the OpenClaw
    ``extractDigestField`` helper.
    """
    needle = f"- {prefix}:"
    for line in lines:
        if line.startswith(needle):
            value = line[len(needle) :].strip()
            return value or None
    return None


def _extract_integer_field(lines: list[str], prefix: str) -> int:
    """Return the integer value of the
    ``- {prefix}: N`` line.

    Mirrors the OpenClaw
    ``extractIntegerField`` helper.
    """
    raw = _extract_digest_field(lines, prefix)
    if not raw:
        return 0
    match = re.search(r"\d+", raw)
    return int(match.group(0)) if match else 0


def _extract_preference_signals(lines: list[str]) -> list[str]:
    """Return the list of preference signals
    from the digest (after the
    ``- Preference signals:`` line).

    Mirrors the OpenClaw
    ``extractPreferenceSignals`` helper.
    """
    out: list[str] = []
    started = False
    for line in lines:
        if line.startswith("- Preference signals:"):
            if "none detected" in line:
                return []
            started = True
            continue
        if not started:
            continue
        trimmed = line.strip()
        if not trimmed.startswith("- "):
            break
        signal = trimmed[2:].strip()
        if signal:
            out.append(signal)
    return out


def _resolve_topic(labels: list[str]) -> tuple[str, str]:
    """Pick the first ``topic/`` / ``area/`` /
    ``domain/`` label, fall back to
    ``"topic/other"``.

    Mirrors the OpenClaw
    ``resolveTopic`` helper.
    """
    for prefix in ("topic/", "area/", "domain/"):
        for label in labels:
            if label.startswith(prefix):
                return label, _humanize_label_suffix(label)
    return "topic/other", _humanize_label_suffix("topic/other")


def _humanize_label_suffix(label: str) -> str:
    """Return the human-readable form of a
    ``topic/`` label.

    Mirrors the OpenClaw
    ``humanizeLabelSuffix`` helper.
    """
    suffix = label.split("/", 1)[1] if "/" in label else label
    parts = [p for p in re.split(r"[/-]", suffix) if p]
    return " ".join(p[:1].upper() + p[1:] for p in parts)


def _shorten_sentence(value: str, max_length: int = 180) -> str:
    """Truncate ``value`` to ``max_length``
    characters (rune-safe).

    Mirrors the OpenClaw
    ``shortenSentence`` helper.
    """
    compact = re.sub(r"\s+", " ", value).strip()
    if len(compact) <= max_length:
        return compact
    return compact[: max_length - 1].rstrip() + "…"


def reset_memory_wiki_import_insights_state_for_tests() -> None:
    """Reset module-level state (test-only helper)."""
    return


async def list_memory_wiki_import_insights(
    config: ResolvedMemoryWikiConfig,
) -> MemoryWikiImportInsightsStatus:
    """List the per-vault import insights.

    Mirrors the OpenClaw
    :func:`listMemoryWikiImportInsights`
    (a focused port — the full heuristic
    port is in 4.3g-mr3).
    """
    pages = read_queryable_wiki_pages(config.vault.path)
    items: list[MemoryWikiImportInsightItem] = []
    for page in pages:
        if page.page.kind != "source":
            continue
        raw = page.raw
        digest_lines = _extract_heading_section(raw, "Digest")
        if not digest_lines:
            continue
        status_raw = _extract_digest_field(digest_lines, "Status") or "available"
        status: DigestStatus = "withheld" if status_raw.lower() == "withheld" else "available"
        labels_raw = _extract_digest_field(digest_lines, "Labels") or ""
        labels = [s.strip() for s in labels_raw.split(",") if s.strip()]
        topic_key, topic_label = _resolve_topic(labels)
        risk_level_raw = _extract_digest_field(digest_lines, "Risk") or "unknown"
        risk_level: RiskLevel = (
            risk_level_raw.lower()  # type: ignore[assignment]
            if risk_level_raw.lower() in ("low", "medium", "high", "unknown")
            else "unknown"
        )
        risk_reasons_raw = _extract_digest_field(digest_lines, "Risk reasons") or ""
        risk_reasons = [s.strip() for s in risk_reasons_raw.split(",") if s.strip()]
        user_count = _extract_integer_field(digest_lines, "User messages")
        assistant_count = _extract_integer_field(digest_lines, "Assistant messages")
        active_count = _extract_integer_field(digest_lines, "Active branch")
        preference_signals = _extract_preference_signals(digest_lines)
        first_user_line = _extract_digest_field(digest_lines, "First user line")
        assistant_opener = _extract_digest_field(digest_lines, "Assistant opener")
        updated_at = _extract_digest_field(digest_lines, "Updated at")
        items.append(
            MemoryWikiImportInsightItem(
                pagePath=page.page.relative_path,
                title=page.page.title,
                riskLevel=risk_level,
                riskReasons=risk_reasons,
                labels=labels,
                topicKey=topic_key,
                topicLabel=topic_label,
                digestStatus=status,
                activeBranchMessages=active_count,
                userMessageCount=user_count,
                assistantMessageCount=assistant_count,
                summary=_shorten_sentence(assistant_opener or first_user_line or page.page.title),
                preferenceSignals=preference_signals,
                firstUserLine=first_user_line,
                assistantOpener=assistant_opener,
                updatedAt=updated_at,
            )
        )

    # Group by topic_key.
    clusters_by_key: dict[str, list[MemoryWikiImportInsightItem]] = {}
    for item in items:
        clusters_by_key.setdefault(item.topicKey, []).append(item)
    clusters: list[MemoryWikiImportInsightCluster] = []
    for key, group in clusters_by_key.items():
        first = group[0]
        clusters.append(
            MemoryWikiImportInsightCluster(
                key=key,
                label=first.topicLabel,
                itemCount=len(group),
                highRiskCount=sum(1 for i in group if i.riskLevel == "high"),
                withheldCount=sum(1 for i in group if i.digestStatus == "withheld"),
                preferenceSignalCount=sum(1 for i in group if i.preferenceSignals),
                items=group,
                updatedAt=first.updatedAt,
            )
        )
    return MemoryWikiImportInsightsStatus(
        sourceType="chatgpt",
        totalItems=len(items),
        totalClusters=len(clusters),
        clusters=clusters,
    )


__all__ = [
    "DigestStatus",
    "MemoryWikiImportInsightCluster",
    "MemoryWikiImportInsightItem",
    "MemoryWikiImportInsightsStatus",
    "RiskLevel",
    "list_memory_wiki_import_insights",
    "reset_memory_wiki_import_insights_state_for_tests",
]
