"""memory_core.dreaming_shadow_trial — preview dreaming output without writing.

OpenClaw parity: mirrors ``extensions/memory-core/src/dreaming-shadow-trial.ts``
(227 LOC). The shadow trial is a "dry run" that reports whether a
candidate dream would be helpful / neutral / harmful without actually
promoting it to durable memory.

Public API:
- ``resolve_dreaming_shadow_trial_recommendation(verdict)`` — verdict
  → recommendation mapping.
- ``default_dreaming_shadow_trial_report_path(params)`` — compute
  the default report file path
  (``<workspace>/memory/dreaming/shadow-trials/<day>/<hash>.md``).
- ``build_dreaming_shadow_trial_report(input)`` — build the report
  (sync, no file IO). Returns a dict with normalized fields + a
  ``markdown`` string.
- ``write_dreaming_shadow_trial_report(input)`` — write the report
  to disk (atomic). Requires ``workspace_dir`` to resolve a path.

Key port decisions:
- Verdict → recommendation mapping is verbatim:
  helpful → promote, neutral → defer, harmful → reject.
- The "report-only" promotion action is a constant — shadow trials
  never actually promote.
- Content hash uses SHA-256 of a JSON-stringified list of normalized
  fields, sliced to 12 hex chars (matches OpenClaw's
  ``resolveReportContentHash``).
- The default report path uses ``formatMemoryDreamingDay`` (already
  ported in ``dreaming_markdown._format_memory_dreaming_day``) for
  the per-day subdir.
- Required text fields (candidate, trialPrompt, baselineOutcome,
  candidateOutcome, reason) are normalized: trim + collapse
  whitespace. Empty values raise ``ValueError``.
- ``riskFlags`` and ``evidenceRefs`` are optional lists; if empty
  after trimming, the markdown uses the fallback
  ``"none recorded"`` / ``"none supplied"`` placeholders.
- ``write_dreaming_shadow_trial_report`` uses atomic write
  (tempfile + os.replace) for crash safety.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from typing import Literal, TypedDict

from .dreaming_markdown import _format_memory_dreaming_day

# ── Types ──────────────────────────────────────────────────────────────

DreamingShadowTrialVerdict = Literal["helpful", "neutral", "harmful"]
DreamingShadowTrialRecommendation = Literal["promote", "defer", "reject"]
DreamingShadowTrialPromotionAction = Literal["report-only"]


class DreamingShadowTrialInput(TypedDict, total=False):
    candidate: str
    trialPrompt: str
    baselineOutcome: str
    candidateOutcome: str
    verdict: str  # DreamingShadowTrialVerdict
    reason: str
    riskFlags: list[str]
    evidenceRefs: list[str]
    workspaceDir: str
    reportPath: str
    nowMs: int
    timezone: str


class DreamingShadowTrialReport(TypedDict, total=False):
    candidate: str
    trialPrompt: str
    baselineOutcome: str
    candidateOutcome: str
    verdict: str
    recommendation: str  # DreamingShadowTrialRecommendation
    reason: str
    riskFlags: list[str]
    evidenceRefs: list[str]
    promotionAction: str  # "report-only"
    reportPath: str
    markdown: str


# ── Internal helpers ───────────────────────────────────────────────────


def _normalize_required_text(value: str, label: str) -> str:
    """Trim + collapse whitespace; raise ``ValueError`` if empty.

    Mirrors OpenClaw's ``normalizeRequiredText``. Used for the
    five required text fields.
    """
    if not isinstance(value, str):
        raise ValueError(f"dreaming shadow trial requires {label}")
    normalized = " ".join(value.split())
    if not normalized:
        raise ValueError(f"dreaming shadow trial requires {label}")
    return normalized


def _normalize_list(values: list[str] | None, fallback: str) -> list[str]:
    """Trim + drop empty; return ``[fallback]`` if the result is empty.

    Mirrors OpenClaw's ``normalizeList``. Used for the markdown
    rendering of optional list fields.
    """
    normalized = [v.strip() for v in (values or []) if isinstance(v, str) and v.strip()]
    return normalized if normalized else [fallback]


def _normalize_data_list(values: list[str] | None) -> list[str]:
    """Trim + drop empty; return ``[]`` if all entries are empty.

    Mirrors OpenClaw's ``normalizeDataList``. Used for the normalized
    field value of optional lists.
    """
    return [v.strip() for v in (values or []) if isinstance(v, str) and v.strip()]


def _format_list(values: list[str]) -> str:
    """Render a list as ``- item`` bullet lines, joined by ``\\n``.

    Mirrors OpenClaw's ``formatList``.
    """
    return "\n".join(f"- {value}" for value in values)


def _resolve_report_content_hash(
    candidate: str,
    trial_prompt: str,
    baseline_outcome: str,
    candidate_outcome: str,
    verdict: str,
    reason: str,
    risk_flags: list[str],
    evidence_refs: list[str],
) -> str:
    """Stable SHA-256 of the report's normalized content (12 hex chars).

    Mirrors OpenClaw's ``resolveReportContentHash``. Used to disambiguate
    multiple shadow-trial reports for the same day.
    """
    seed = json.dumps(
        [
            candidate,
            trial_prompt,
            baseline_outcome,
            candidate_outcome,
            verdict,
            reason,
            risk_flags,
            evidence_refs,
        ]
    )
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:12]


# ── Public API ─────────────────────────────────────────────────────────


def resolve_dreaming_shadow_trial_recommendation(
    verdict: str,
) -> str:
    """Map a verdict to a recommendation.

    Mirrors OpenClaw's ``resolveDreamingShadowTrialRecommendation``:
    ``helpful`` → ``promote``, ``harmful`` → ``reject``,
    ``neutral`` (and any unrecognized verdict) → ``defer``.
    """
    if verdict == "helpful":
        return "promote"
    if verdict == "harmful":
        return "reject"
    return "defer"


def default_dreaming_shadow_trial_report_path(
    workspace_dir: str,
    candidate: str,
    trial_prompt: str,
    baseline_outcome: str,
    candidate_outcome: str,
    verdict: str,
    reason: str,
    risk_flags: list[str] | None = None,
    evidence_refs: list[str] | None = None,
    now_ms: int | None = None,
    timezone_name: str | None = None,
) -> str:
    """Return the default shadow-trial report path.

    Mirrors OpenClaw's ``defaultDreamingShadowTrialReportPath``. Path
    shape:
    ``<workspace>/memory/dreaming/shadow-trials/<YYYY-MM-DD>/<hash>.md``.

    Required text fields are normalized before hashing. The hash
    is content-derived so two trials with the same content for the
    same day collapse to the same file.
    """
    if now_ms is not None:
        try:
            now = int(now_ms)
        except (TypeError, ValueError):
            now = _now_ms()
    else:
        now = _now_ms()
    day = _format_memory_dreaming_day(now, timezone_name)
    content_hash = _resolve_report_content_hash(
        _normalize_required_text(candidate, "candidate"),
        _normalize_required_text(trial_prompt, "trialPrompt"),
        _normalize_required_text(baseline_outcome, "baselineOutcome"),
        _normalize_required_text(candidate_outcome, "candidateOutcome"),
        verdict,
        _normalize_required_text(reason, "reason"),
        _normalize_data_list(risk_flags),
        _normalize_data_list(evidence_refs),
    )
    return os.path.join(
        workspace_dir, "memory", "dreaming", "shadow-trials", day, f"{content_hash}.md"
    )


def _resolve_report_path(
    workspace_dir: str | None,
    candidate: str,
    trial_prompt: str,
    baseline_outcome: str,
    candidate_outcome: str,
    verdict: str,
    reason: str,
    risk_flags: list[str],
    evidence_refs: list[str],
    report_path: str | None,
    now_ms: int | None,
    timezone_name: str | None,
) -> str | None:
    """Resolve the report path from explicit ``reportPath`` or defaults.

    Mirrors OpenClaw's ``resolveReportPath``. Returns ``None`` if no
    workspace is provided and no explicit report path is given.
    """
    if report_path:
        if os.path.isabs(report_path):
            return report_path
        if not workspace_dir:
            raise ValueError("dreaming shadow trial relative reportPath requires workspaceDir")
        return os.path.join(workspace_dir, report_path)
    if not workspace_dir:
        return None
    return default_dreaming_shadow_trial_report_path(
        workspace_dir=workspace_dir,
        candidate=candidate,
        trial_prompt=trial_prompt,
        baseline_outcome=baseline_outcome,
        candidate_outcome=candidate_outcome,
        verdict=verdict,
        reason=reason,
        risk_flags=risk_flags,
        evidence_refs=evidence_refs,
        now_ms=now_ms,
        timezone_name=timezone_name,
    )


def _now_ms() -> int:
    """Return the current epoch milliseconds (Python equivalent of ``Date.now()``)."""
    import time

    return int(time.time() * 1000)


def build_dreaming_shadow_trial_report(
    input: DreamingShadowTrialInput,
) -> DreamingShadowTrialReport:
    """Build the shadow-trial report (sync, no file IO).

    Mirrors OpenClaw's ``buildDreamingShadowTrialReport``. Required
    fields (``candidate``, ``trialPrompt``, ``baselineOutcome``,
    ``candidateOutcome``, ``verdict``, ``reason``) are normalized;
    empty values raise ``ValueError``. Returns a dict containing the
    normalized fields + a ``markdown`` body.

    The ``promotionAction`` field is always ``"report-only"`` — shadow
    trials never actually promote to durable memory.
    """
    candidate = _normalize_required_text(input["candidate"], "candidate")
    trial_prompt = _normalize_required_text(input["trialPrompt"], "trialPrompt")
    baseline_outcome = _normalize_required_text(input["baselineOutcome"], "baselineOutcome")
    candidate_outcome = _normalize_required_text(input["candidateOutcome"], "candidateOutcome")
    reason = _normalize_required_text(input["reason"], "reason")
    risk_flags = _normalize_data_list(input.get("riskFlags"))
    evidence_refs = _normalize_data_list(input.get("evidenceRefs"))
    verdict = input["verdict"]
    recommendation = resolve_dreaming_shadow_trial_recommendation(verdict)
    report_path = _resolve_report_path(
        workspace_dir=input.get("workspaceDir"),
        candidate=candidate,
        trial_prompt=trial_prompt,
        baseline_outcome=baseline_outcome,
        candidate_outcome=candidate_outcome,
        verdict=verdict,
        reason=reason,
        risk_flags=risk_flags,
        evidence_refs=evidence_refs,
        report_path=input.get("reportPath"),
        now_ms=input.get("nowMs"),
        timezone_name=input.get("timezone"),
    )

    markdown = "\n".join(
        [
            "# Dreaming Shadow Trial Report",
            "",
            f"candidate: {candidate}",
            f"trial prompt: {trial_prompt}",
            f"baseline outcome: {baseline_outcome}",
            f"candidate outcome: {candidate_outcome}",
            f"verdict: {verdict}",
            f"recommendation: {recommendation}",
            f"reason: {reason}",
            "risk flags:",
            _format_list(_normalize_list(risk_flags, "none recorded")),
            "evidence refs:",
            _format_list(_normalize_list(evidence_refs, "none supplied")),
            "promotion action: report-only",
            "",
        ]
    )

    report: DreamingShadowTrialReport = {
        "candidate": candidate,
        "trialPrompt": trial_prompt,
        "baselineOutcome": baseline_outcome,
        "candidateOutcome": candidate_outcome,
        "verdict": verdict,
        "recommendation": recommendation,
        "reason": reason,
        "riskFlags": risk_flags,
        "evidenceRefs": evidence_refs,
        "promotionAction": "report-only",
        "markdown": markdown,
    }
    if report_path is not None:
        report["reportPath"] = report_path
    return report


def write_dreaming_shadow_trial_report(
    input: DreamingShadowTrialInput,
) -> DreamingShadowTrialReport:
    """Build + atomically write the shadow-trial report.

    Mirrors OpenClaw's ``writeDreamingShadowTrialReport``. Returns the
    report dict (which now includes the resolved ``reportPath``).
    Raises ``ValueError`` when no ``workspaceDir`` and no explicit
    ``reportPath`` is provided (the path can't be resolved).

    The write is atomic (tempfile + os.replace) so a crash mid-write
    doesn't truncate the report.
    """
    report = build_dreaming_shadow_trial_report(input)
    if not report.get("reportPath"):
        raise ValueError("dreaming shadow trial report path could not be resolved")
    report_path = report["reportPath"]
    parent = os.path.dirname(report_path) or "."
    os.makedirs(parent, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{os.path.basename(report_path)}.tmp.", dir=parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(report["markdown"])
        os.replace(tmp, report_path)
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise
    return report


__all__ = [
    # Types
    "DreamingShadowTrialVerdict",
    "DreamingShadowTrialRecommendation",
    "DreamingShadowTrialPromotionAction",
    "DreamingShadowTrialInput",
    "DreamingShadowTrialReport",
    # API
    "resolve_dreaming_shadow_trial_recommendation",
    "default_dreaming_shadow_trial_report_path",
    "build_dreaming_shadow_trial_report",
    "write_dreaming_shadow_trial_report",
]
