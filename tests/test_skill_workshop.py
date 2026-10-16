"""Tests for src/skills/skill_workshop.py.

Mirrors tests of docs/tools/skill-workshop.md and src/skills/workshop in OpenClaw.
"""

from __future__ import annotations

import pytest

from src.skills.skill_workshop import (
    SkillWorkshopService,
    SupportFile,
)


def test_create_proposal_valid(tmp_path):
    svc = SkillWorkshopService(workspace_dir=tmp_path)
    proposal = svc.create_proposal(
        name="morning-catchup",
        description="Daily inbox catch-up routine",
        content="---\nname: morning-catchup\n---\nRun morning routine...",
        support_files=[SupportFile("assets/template.txt", "Hello World")],
    )

    assert proposal.id == "proposal-1"
    assert proposal.status == "pending"
    assert len(proposal.support_files) == 1


def test_create_proposal_exceeds_description_bytes(tmp_path):
    svc = SkillWorkshopService(workspace_dir=tmp_path)
    long_desc = "A" * 200

    with pytest.raises(ValueError, match="description exceeds max length"):
        svc.create_proposal(
            name="test-skill",
            description=long_desc,
            content="content",
        )


def test_create_proposal_invalid_support_dir(tmp_path):
    svc = SkillWorkshopService(workspace_dir=tmp_path)

    with pytest.raises(ValueError, match="Support file .* must be in one of"):
        svc.create_proposal(
            name="test-skill",
            description="desc",
            content="content",
            support_files=[SupportFile("invalid_dir/file.txt", "content")],
        )


def test_apply_proposal(tmp_path):
    svc = SkillWorkshopService(workspace_dir=tmp_path)
    proposal = svc.create_proposal(
        name="my-skill",
        description="My skill description",
        content="---\nname: my-skill\n---\nSkill content",
        support_files=[SupportFile("assets/config.json", "{}")],
    )

    applied = svc.apply_proposal(proposal.id, reason="User approved")
    assert applied.status == "applied"

    target_skill = tmp_path / "skills" / "my-skill" / "SKILL.md"
    target_asset = tmp_path / "skills" / "my-skill" / "assets" / "config.json"

    assert target_skill.exists()
    assert target_skill.read_text(encoding="utf-8") == "---\nname: my-skill\n---\nSkill content"
    assert target_asset.exists()
    assert target_asset.read_text(encoding="utf-8") == "{}"
