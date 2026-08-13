"""Skill runtime executor — mirrors OpenClaw ``src/skills/runtime/``.

Renders skills into prompt snapshots and resolves active skills for user input context.
"""

from __future__ import annotations

import re
from typing import Sequence
from ..types import SkillEntry, SkillSnapshot, Skill


def skills_to_snapshot(entries: Sequence[SkillEntry]) -> SkillSnapshot:
    """Build a prompt snapshot and summary metadata list from loaded skill entries."""
    prompt_parts: list[str] = ["# Available Skills\n"]
    summary_skills: list[dict[str, str]] = []
    resolved: list[Skill] = []

    for entry in entries:
        skill = entry.skill
        meta = entry.metadata
        emoji_prefix = f"{meta.emoji} " if meta and meta.emoji else ""

        summary_skills.append({
            "name": skill.name,
            "description": skill.description,
            "source": skill.source,
        })
        resolved.append(skill)

        prompt_parts.append(f"## {emoji_prefix}{skill.name}")
        prompt_parts.append(f"Description: {skill.description}")
        if skill.body:
            prompt_parts.append(f"\n{skill.body}\n")
        prompt_parts.append("")

    prompt = "\n".join(prompt_parts).strip()
    return SkillSnapshot(
        prompt=prompt,
        skills=summary_skills,
        resolved_skills=resolved,
        version=3,
    )


def resolve_active_skills(
    query: str,
    available_entries: Sequence[SkillEntry],
) -> list[SkillEntry]:
    """Find skill entries relevant to query or marked 'always=True'."""
    matched: list[SkillEntry] = []
    query_lower = query.lower()

    for entry in available_entries:
        if entry.metadata and entry.metadata.always:
            matched.append(entry)
            continue

        # Match by name or description keywords
        name_kws = re.findall(r"\w+", entry.skill.name.lower())
        desc_kws = [w for w in re.findall(r"\w+", entry.skill.description.lower()) if len(w) > 3]

        if any(kw in query_lower for kw in name_kws if len(kw) > 2) or any(kw in query_lower for kw in desc_kws):
            matched.append(entry)

    return matched


__all__ = ["resolve_active_skills", "skills_to_snapshot"]
