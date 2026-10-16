"""jarvis.skills.skill_interpolation — Skill template interpolation & direct tool dispatch.

OpenClaw parity: mirrors
``openclaw-main/docs/tools/creating-skills.md`` and
``openclaw-main/src/skills/discovery/chat-command-invocation.ts``.

Features:
- `interpolate_skill_base_dir()`: Resolves ``{baseDir}`` placeholders against skill directory paths.
- `resolve_direct_tool_dispatch()`: Evaluates ``command-dispatch: tool`` slash commands for model bypass.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .skill_loading import SkillDescriptor


def interpolate_skill_base_dir(content: str, base_dir: str | Path) -> str:
    """Replace all `{baseDir}` placeholders in skill markdown with the skill's absolute directory path."""
    clean_dir = str(Path(base_dir).resolve())
    return content.replace("{baseDir}", clean_dir)


@dataclass
class DirectToolDispatchInvocation:
    tool_name: str
    params: dict[str, Any]
    skill_name: str
    command_name: str


def resolve_direct_tool_dispatch(
    raw_message: str,
    skills: list[SkillDescriptor],
) -> DirectToolDispatchInvocation | None:
    """Evaluate whether a slash command targets a skill with `command-dispatch: tool`."""
    trimmed = raw_message.strip()
    if not trimmed.startswith("/"):
        return None

    # Parse /command_name [args...]
    parts = trimmed[1:].split(maxsplit=1)
    cmd_name = parts[0].lower().replace("_", "-")
    raw_args = parts[1] if len(parts) > 1 else ""

    # Find matching skill
    for skill in skills:
        if not skill.enabled or skill.metadata.command_dispatch != "tool":
            continue

        skill_cmd_name = skill.name.lower().replace("_", "-")
        if cmd_name == skill_cmd_name:
            target_tool = skill.metadata.command_tool or skill.name
            return DirectToolDispatchInvocation(
                tool_name=target_tool,
                params={
                    "command": raw_args,
                    "commandName": cmd_name,
                    "skillName": skill.name,
                },
                skill_name=skill.name,
                command_name=cmd_name,
            )

    return None


__all__ = [
    "DirectToolDispatchInvocation",
    "interpolate_skill_base_dir",
    "resolve_direct_tool_dispatch",
]
