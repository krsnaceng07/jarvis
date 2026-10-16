"""Tests for src/skills/skill_loading.py.

Mirrors tests of docs/tools/skills.md and src/skills/loading/config.ts in OpenClaw.
"""

from __future__ import annotations


from src.skills.skill_loading import (
    SkillDescriptor,
    SkillMetadata,
    SkillSourcePrecedence,
    evaluate_skill_eligibility,
    filter_agent_skills,
    resolve_skill_discovery_hierarchy,
)


def test_resolve_skill_discovery_hierarchy():
    roots = resolve_skill_discovery_hierarchy(workspace_dir="/tmp/workspace")
    assert len(roots) >= 5
    assert roots[0][0] == SkillSourcePrecedence.WORKSPACE
    assert roots[1][0] == SkillSourcePrecedence.PROJECT_AGENT
    assert roots[2][0] == SkillSourcePrecedence.PERSONAL_AGENT


def test_evaluate_skill_eligibility_os():
    meta = SkillMetadata(name="mac-only", description="Mac skill", os_target=["darwin"])
    # If running on win32, should return False
    import sys
    if sys.platform != "darwin":
        assert evaluate_skill_eligibility(meta) is False


def test_evaluate_skill_eligibility_env():
    meta = SkillMetadata(name="api-skill", description="API skill", requires_env=["NONEXISTENT_KEY_12345"])
    assert evaluate_skill_eligibility(meta) is False


def test_filter_agent_skills_allowlist():
    sk1 = SkillDescriptor("s1", "github", "GitHub skill", "/path/1", SkillSourcePrecedence.WORKSPACE, SkillMetadata("github", "GH"))
    sk2 = SkillDescriptor("s2", "weather", "Weather skill", "/path/2", SkillSourcePrecedence.WORKSPACE, SkillMetadata("weather", "W"))

    skills = [sk1, sk2]

    cfg = {
        "agents": {
            "defaults": {"skills": ["github", "weather"]},
            "entries": {
                "writer": {"default": True},
                "docs": {"skills": ["docs-search"]},
                "locked-down": {"skills": []},
            },
        }
    }

    # Writer inherits defaults
    filtered_writer = filter_agent_skills(skills, "writer", cfg)
    assert len(filtered_writer) == 2

    # Docs overrides with docs-search only
    filtered_docs = filter_agent_skills(skills, "docs", cfg)
    assert len(filtered_docs) == 0

    # Locked-down exposes no skills
    filtered_locked = filter_agent_skills(skills, "locked-down", cfg)
    assert len(filtered_locked) == 0
