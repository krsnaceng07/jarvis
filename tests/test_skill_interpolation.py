"""Tests for src/skills/skill_interpolation.py.

Mirrors tests of docs/tools/creating-skills.md and src/skills/discovery/chat-command-invocation.ts in OpenClaw.
"""

from __future__ import annotations


from src.skills.skill_interpolation import (
    interpolate_skill_base_dir,
    resolve_direct_tool_dispatch,
)
from src.skills.skill_loading import (
    SkillDescriptor,
    SkillMetadata,
    SkillSourcePrecedence,
)


def test_interpolate_skill_base_dir(tmp_path):
    content = "Run script at {baseDir}/scripts/run.sh"
    res = interpolate_skill_base_dir(content, tmp_path)
    assert str(tmp_path.resolve()) in res
    assert "{baseDir}" not in res


def test_resolve_direct_tool_dispatch():
    meta = SkillMetadata(
        name="hello-world",
        description="Greeting skill",
        command_dispatch="tool",
        command_tool="exec",
    )
    sk = SkillDescriptor(
        id="hello-world",
        name="hello-world",
        description="Greeting skill",
        skill_path="/tmp/skills/hello-world",
        precedence=SkillSourcePrecedence.WORKSPACE,
        metadata=meta,
    )

    inv = resolve_direct_tool_dispatch("/hello-world --name John", [sk])
    assert inv is not None
    assert inv.tool_name == "exec"
    assert inv.params["command"] == "--name John"
    assert inv.params["commandName"] == "hello-world"
    assert inv.params["skillName"] == "hello-world"


def test_resolve_direct_tool_dispatch_no_match():
    meta = SkillMetadata(name="hello-world", description="Greeting skill")
    sk = SkillDescriptor(
        id="hello-world",
        name="hello-world",
        description="Greeting skill",
        skill_path="/tmp/skills/hello-world",
        precedence=SkillSourcePrecedence.WORKSPACE,
        metadata=meta,
    )

    inv = resolve_direct_tool_dispatch("/hello-world", [sk])
    assert inv is None
