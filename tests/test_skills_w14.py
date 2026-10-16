"""Tests for Wave 14 — Skills Runtime (discovery, loading, security, runtime)."""

from __future__ import annotations

from pathlib import Path

from src.skills import (
    SkillEligibilityContext,
    load_skill_from_dir,
    resolve_active_skills,
    skills_to_snapshot,
    validate_skill_eligibility,
    validate_skill_path_containment,
)


def test_load_skill_from_dir(tmp_path: Path):
    skill_dir = tmp_path / "weather"
    skill_dir.mkdir()
    skill_md = skill_dir / "SKILL.md"
    skill_md.write_text(
        "---\n"
        "name: weather\n"
        "description: Get weather information\n"
        "emoji: 🌤️\n"
        "always: false\n"
        "---\n\n"
        "Use when user asks about weather forecast.\n",
        encoding="utf-8",
    )

    entry = load_skill_from_dir(skill_dir, source="bundled")
    assert entry is not None
    assert entry.skill.name == "weather"
    assert entry.skill.description == "Get weather information"
    assert entry.metadata is not None
    assert entry.metadata.emoji == "🌤️"


def test_skill_security_containment(tmp_path: Path):
    skill_root = tmp_path / "skills"
    skill_root.mkdir()
    inside_dir = skill_root / "inside"
    inside_dir.mkdir()

    assert validate_skill_path_containment(str(skill_root), str(inside_dir))
    assert not validate_skill_path_containment(str(skill_root), str(tmp_path / "outside"))


def test_skill_eligibility():
    skill_dir = Path("dummy")
    from src.skills.types import Skill, SkillEntry, SkillMetadata

    entry = SkillEntry(
        skill=Skill("test", "desc", "body", "test/SKILL.md", "test"),
        frontmatter={},
        metadata=SkillMetadata(requires_bins=("git",)),
    )

    ctx_has_git = SkillEligibilityContext(has_bins=frozenset({"git"}))
    ctx_no_git = SkillEligibilityContext(has_bins=frozenset({"curl"}))

    assert validate_skill_eligibility(entry, ctx_has_git)
    assert not validate_skill_eligibility(entry, ctx_no_git)


def test_resolve_active_skills_and_snapshot(tmp_path: Path):
    skill_dir = tmp_path / "github"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\nname: github\ndescription: Interact with GitHub issues and PRs\n---\n\nGitHub details.",
        encoding="utf-8",
    )

    entry = load_skill_from_dir(skill_dir)
    assert entry is not None

    active = resolve_active_skills("Please list my open github issues", [entry])
    assert len(active) == 1
    assert active[0].skill.name == "github"

    snapshot = skills_to_snapshot([entry])
    assert "github" in snapshot.prompt
    assert len(snapshot.skills) == 1
