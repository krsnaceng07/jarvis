"""Tests for memory_core.dreaming_shadow_trial — Phase 4.4g.

Mirrors the TypeScript ``test_dreaming-shadow-trial.test.ts`` patterns.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

import pytest

from extensions.memory_core import dreaming_shadow_trial as dst


# ── Verdict → recommendation mapping ───────────────────────────────────


def test_recommendation_helpful_promotes() -> None:
    assert dst.resolve_dreaming_shadow_trial_recommendation("helpful") == "promote"


def test_recommendation_neutral_defers() -> None:
    assert dst.resolve_dreaming_shadow_trial_recommendation("neutral") == "defer"


def test_recommendation_harmful_rejects() -> None:
    assert dst.resolve_dreaming_shadow_trial_recommendation("harmful") == "reject"


def test_recommendation_unknown_defers() -> None:
    """Unknown verdicts fall back to ``defer`` (safe default)."""
    assert dst.resolve_dreaming_shadow_trial_recommendation("garbage") == "defer"


# ── Required text normalization ────────────────────────────────────────


def test_required_text_trims_and_collapses() -> None:
    """Whitespace is collapsed; leading/trailing trimmed."""
    assert dst._normalize_required_text("  hello   world  ", "test") == "hello world"


def test_required_text_empty_raises() -> None:
    """Empty / whitespace-only values raise ``ValueError``."""
    with pytest.raises(ValueError, match="test"):
        dst._normalize_required_text("", "test")
    with pytest.raises(ValueError, match="test"):
        dst._normalize_required_text("   ", "test")
    with pytest.raises(ValueError, match="test"):
        dst._normalize_required_text("\t\n", "test")


# ── List normalization ─────────────────────────────────────────────────


def test_normalize_list_trims() -> None:
    assert dst._normalize_list(["  a  ", "  b  "], "fallback") == ["a", "b"]


def test_normalize_list_drops_empty() -> None:
    assert dst._normalize_list(["a", "", "  ", "b"], "fallback") == ["a", "b"]


def test_normalize_list_uses_fallback_when_empty() -> None:
    assert dst._normalize_list([], "none") == ["none"]
    assert dst._normalize_list(["", "  "], "none") == ["none"]
    assert dst._normalize_list(None, "none") == ["none"]


def test_normalize_data_list_no_fallback() -> None:
    """``normalizeDataList`` returns ``[]`` for empty input (no fallback)."""
    assert dst._normalize_data_list([]) == []
    assert dst._normalize_data_list(None) == []
    assert dst._normalize_data_list(["", "  "]) == []


def test_format_list_bullets() -> None:
    """Lists render as ``- item`` lines joined by ``\\n``."""
    assert dst._format_list(["a", "b"]) == "- a\n- b"


# ── Content hash ───────────────────────────────────────────────────────


def test_content_hash_deterministic() -> None:
    """Same inputs → same hash."""
    a = dst._resolve_report_content_hash("c", "p", "b", "x", "helpful", "r", [], [])
    b = dst._resolve_report_content_hash("c", "p", "b", "x", "helpful", "r", [], [])
    assert a == b


def test_content_hash_differs_per_field() -> None:
    """Changing any field changes the hash."""
    base = dst._resolve_report_content_hash("c", "p", "b", "x", "helpful", "r", [], [])
    candidates = [
        ("c2", "p", "b", "x", "helpful", "r", [], []),
        ("c", "p2", "b", "x", "helpful", "r", [], []),
        ("c", "p", "b2", "x", "helpful", "r", [], []),
        ("c", "p", "b", "x2", "helpful", "r", [], []),
        ("c", "p", "b", "x", "harmful", "r", [], []),
        ("c", "p", "b", "x", "helpful", "r2", [], []),
        ("c", "p", "b", "x", "helpful", "r", ["risk"], []),
        ("c", "p", "b", "x", "helpful", "r", [], ["ev"]),
    ]
    hashes = {dst._resolve_report_content_hash(*cand) for cand in candidates}
    assert len(hashes) == len(candidates)
    assert base not in hashes


def test_content_hash_length() -> None:
    """Hash is exactly 12 hex chars."""
    h = dst._resolve_report_content_hash("c", "p", "b", "x", "helpful", "r", [], [])
    assert len(h) == 12
    int(h, 16)  # Must be valid hex


# ── Default report path ───────────────────────────────────────────────


def test_default_report_path_shape(tmp_path: Path) -> None:
    """Path: ``<workspace>/memory/dreaming/shadow-trials/<day>/<hash>.md``."""
    epoch_ms = int(datetime(2025, 12, 15, 14, 30, tzinfo=timezone.utc).timestamp() * 1000)
    path = dst.default_dreaming_shadow_trial_report_path(
        workspace_dir=str(tmp_path),
        candidate="cand",
        trial_prompt="prompt",
        baseline_outcome="base",
        candidate_outcome="can",
        verdict="helpful",
        reason="because",
        now_ms=epoch_ms,
        timezone_name="UTC",
    )
    expected_suffix = os.path.join("memory", "dreaming", "shadow-trials", "2025-12-15")
    assert expected_suffix in path
    assert path.endswith(".md")
    # Hash filename: 12 hex chars + ".md"
    name = os.path.basename(path)
    stem = name[:-3]  # strip ".md"
    assert len(stem) == 12
    int(stem, 16)


def test_default_report_path_requires_required_text() -> None:
    """Empty required fields raise ``ValueError`` before path resolution."""
    with pytest.raises(ValueError, match="candidate"):
        dst.default_dreaming_shadow_trial_report_path(
            workspace_dir="/tmp",
            candidate="",
            trial_prompt="p",
            baseline_outcome="b",
            candidate_outcome="c",
            verdict="helpful",
            reason="r",
        )


# ── Build report ───────────────────────────────────────────────────────


def _input(**overrides: object) -> dst.DreamingShadowTrialInput:
    """Build a minimal valid input dict (overrides win)."""
    base: dst.DreamingShadowTrialInput = {
        "candidate": "promote me",
        "trialPrompt": "what if?",
        "baselineOutcome": "baseline",
        "candidateOutcome": "candidate",
        "verdict": "helpful",
        "reason": "looks good",
    }
    base.update(overrides)  # type: ignore[typeddict-item]
    return base


def test_build_report_minimal() -> None:
    """Minimal valid input builds a report."""
    report = dst.build_dreaming_shadow_trial_report(_input())
    assert report["candidate"] == "promote me"
    assert report["trialPrompt"] == "what if?"
    assert report["baselineOutcome"] == "baseline"
    assert report["candidateOutcome"] == "candidate"
    assert report["verdict"] == "helpful"
    assert report["recommendation"] == "promote"
    assert report["reason"] == "looks good"
    assert report["promotionAction"] == "report-only"
    assert report["riskFlags"] == []
    assert report["evidenceRefs"] == []
    assert "reportPath" not in report  # no workspace → no path
    # Markdown content
    assert "# Dreaming Shadow Trial Report" in report["markdown"]
    assert "candidate: promote me" in report["markdown"]
    assert "verdict: helpful" in report["markdown"]
    assert "recommendation: promote" in report["markdown"]
    assert "promotion action: report-only" in report["markdown"]
    # No risk flags / evidence → fallback placeholders
    assert "- none recorded" in report["markdown"]
    assert "- none supplied" in report["markdown"]


def test_build_report_with_lists() -> None:
    """Risk flags + evidence refs are rendered as bullets."""
    report = dst.build_dreaming_shadow_trial_report(
        _input(
            riskFlags=["low-confidence", "unverified-source"],
            evidenceRefs=["memory/2025-12-15.md", "memory/2025-12-14.md"],
        )
    )
    assert report["riskFlags"] == ["low-confidence", "unverified-source"]
    assert report["evidenceRefs"] == ["memory/2025-12-15.md", "memory/2025-12-14.md"]
    assert "- low-confidence" in report["markdown"]
    assert "- unverified-source" in report["markdown"]
    assert "- memory/2025-12-15.md" in report["markdown"]
    assert "- memory/2025-12-14.md" in report["markdown"]


def test_build_report_with_workspace(tmp_path: Path) -> None:
    """``workspaceDir`` enables default path resolution."""
    report = dst.build_dreaming_shadow_trial_report(_input(workspaceDir=str(tmp_path)))
    assert "reportPath" in report
    expected_suffix = os.path.join("memory", "dreaming", "shadow-trials")
    assert expected_suffix in report["reportPath"]
    assert report["reportPath"].startswith(str(tmp_path))


def test_build_report_with_explicit_absolute_path() -> None:
    """Absolute ``reportPath`` is used verbatim."""
    report = dst.build_dreaming_shadow_trial_report(
        _input(workspaceDir="/tmp/test-ws", reportPath="/absolute/path.md")
    )
    assert report["reportPath"] == "/absolute/path.md"


def test_build_report_with_relative_path_requires_workspace() -> None:
    """Relative ``reportPath`` is joined to ``workspaceDir``."""
    report = dst.build_dreaming_shadow_trial_report(
        _input(workspaceDir="/tmp/test-ws", reportPath="custom/report.md")
    )
    assert report["reportPath"] == os.path.join("/tmp/test-ws", "custom/report.md")


def test_build_report_relative_path_without_workspace_raises() -> None:
    """Relative ``reportPath`` without ``workspaceDir`` raises."""
    with pytest.raises(ValueError, match="workspaceDir"):
        dst.build_dreaming_shadow_trial_report(_input(reportPath="custom/report.md"))


def test_build_report_normalizes_whitespace() -> None:
    """Required text fields are trimmed + collapsed."""
    report = dst.build_dreaming_shadow_trial_report(
        _input(
            candidate="  hello   world  ",
            trialPrompt="\twhat if?\n",
            baselineOutcome=" base ",
            candidateOutcome=" can ",
            reason="  because\n\n  ",
        )
    )
    assert report["candidate"] == "hello world"
    assert report["trialPrompt"] == "what if?"
    assert report["baselineOutcome"] == "base"
    assert report["candidateOutcome"] == "can"
    assert report["reason"] == "because"


def test_build_report_required_field_missing_raises() -> None:
    """Each required text field has its own error message."""
    with pytest.raises(ValueError, match="candidate"):
        dst.build_dreaming_shadow_trial_report(_input(candidate=""))
    with pytest.raises(ValueError, match="trialPrompt"):
        dst.build_dreaming_shadow_trial_report(_input(trialPrompt=""))
    with pytest.raises(ValueError, match="baselineOutcome"):
        dst.build_dreaming_shadow_trial_report(_input(baselineOutcome=""))
    with pytest.raises(ValueError, match="candidateOutcome"):
        dst.build_dreaming_shadow_trial_report(_input(candidateOutcome=""))
    with pytest.raises(ValueError, match="reason"):
        dst.build_dreaming_shadow_trial_report(_input(reason=""))


def test_build_report_recommendation_per_verdict() -> None:
    """Recommendation is derived from the verdict."""
    for verdict, expected in [
        ("helpful", "promote"),
        ("neutral", "defer"),
        ("harmful", "reject"),
    ]:
        report = dst.build_dreaming_shadow_trial_report(_input(verdict=verdict))
        assert report["recommendation"] == expected


# ── Write report ───────────────────────────────────────────────────────


def test_write_report_to_disk(tmp_path: Path) -> None:
    """Report file is created with the markdown content."""
    report = dst.write_dreaming_shadow_trial_report(_input(workspaceDir=str(tmp_path)))
    assert report.get("reportPath") is not None
    assert os.path.isfile(report["reportPath"])
    content = open(report["reportPath"], encoding="utf-8").read()
    assert content == report["markdown"]
    assert "# Dreaming Shadow Trial Report" in content
    # Parent dir was created
    parent = os.path.dirname(report["reportPath"])
    assert os.path.isdir(parent)


def test_write_report_atomic_crash_safety(tmp_path: Path) -> None:
    """Atomic write: no temp file is left behind on success."""
    report = dst.write_dreaming_shadow_trial_report(_input(workspaceDir=str(tmp_path)))
    parent = os.path.dirname(report["reportPath"])
    # No .tmp.* files left
    for entry in os.listdir(parent):
        assert ".tmp." not in entry


def test_write_report_creates_subdirs(tmp_path: Path) -> None:
    """``memory/dreaming/shadow-trials/<day>/`` is created if missing."""
    report = dst.write_dreaming_shadow_trial_report(_input(workspaceDir=str(tmp_path)))
    subdir = os.path.dirname(report["reportPath"])
    assert os.path.isdir(subdir)
    assert "memory" in subdir
    assert "dreaming" in subdir
    assert "shadow-trials" in subdir


def test_write_report_without_workspace_raises() -> None:
    """No ``workspaceDir`` and no explicit ``reportPath`` → raises."""
    with pytest.raises(ValueError, match="could not be resolved"):
        dst.write_dreaming_shadow_trial_report(_input())


def test_write_report_with_explicit_absolute_path(tmp_path: Path) -> None:
    """Absolute ``reportPath`` is honored without requiring ``workspaceDir``."""
    explicit = str(tmp_path / "explicit.md")
    report = dst.write_dreaming_shadow_trial_report(_input(reportPath=explicit))
    assert report["reportPath"] == explicit
    assert os.path.isfile(explicit)


def test_write_report_overwrites_existing(tmp_path: Path) -> None:
    """Re-running with same content overwrites the existing file."""
    args = _input(workspaceDir=str(tmp_path))
    first = dst.write_dreaming_shadow_trial_report(args)
    second = dst.write_dreaming_shadow_trial_report(args)
    # Same hash → same path
    assert first["reportPath"] == second["reportPath"]
    assert os.path.isfile(first["reportPath"])
