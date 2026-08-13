"""Skill discovery scanner — mirrors OpenClaw ``src/skills/discovery/``.

Discovers all skills across 3 tiers:
  1. Workspace root `skills/<id>/SKILL.md` or package bundled skills
  2. Plugin-contributed skills
  3. User workspace `~/.jarvis/skills/<id>/SKILL.md`
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from ..loading.loader import load_skill_from_dir
from ..security.validator import validate_skill_path_containment, validate_skill_eligibility
from ..types import SkillEntry, SkillEligibilityContext, SkillTelemetrySource

_log = logging.getLogger("jarvis.skills.discovery")


def scan_skills_directory(
    root: Path,
    source: SkillTelemetrySource = "bundled",
    plugin_id: str | None = None,
    context: SkillEligibilityContext | None = None,
) -> list[SkillEntry]:
    """Scan a directory for skill subdirectories containing SKILL.md."""
    if not root.exists() or not root.is_dir():
        return []

    entries: list[SkillEntry] = []
    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue

        # Security check: containment
        if not validate_skill_path_containment(str(root), str(child)):
            _log.warning("skills: containment check failed for %s", child)
            continue

        entry = load_skill_from_dir(child, source=source, plugin_id=plugin_id)
        if entry is None:
            continue

        # Eligibility check
        if not validate_skill_eligibility(entry, context):
            _log.debug("skills: skill %s not eligible in current context", entry.skill.name)
            continue

        entries.append(entry)

    return entries


def discover_all_skills(
    workspace_skills_dir: Path | None = None,
    workspace_agents_skills_dir: Path | None = None,
    home_agents_skills_dir: Path | None = None,
    user_skills_dir: Path | None = None,
    plugin_skill_dirs: list[dict[str, str]] | None = None,
    bundled_skills_dir: Path | None = None,
    context: SkillEligibilityContext | None = None,
) -> list[SkillEntry]:
    """Discover skills from all sources and return deduped by skill name (last wins)."""
    by_name: dict[str, SkillEntry] = {}

    # 1. Plugin (extra) skills
    if plugin_skill_dirs:
        for item in plugin_skill_dirs:
            p_dir = Path(item.get("dir", ""))
            p_id = item.get("plugin_id")
            for entry in scan_skills_directory(p_dir, source="plugin", plugin_id=p_id, context=context):
                by_name[entry.skill.name] = entry

    # 2. Bundled skills
    if bundled_skills_dir:
        for entry in scan_skills_directory(bundled_skills_dir, source="bundled", context=context):
            by_name[entry.skill.name] = entry

    # 3. User workspace skills (~/.jarvis/skills)
    user_dir = user_skills_dir or (Path.home() / ".jarvis" / "skills")
    if user_dir.exists():
        for entry in scan_skills_directory(user_dir, source="workspace", context=context):
            by_name[entry.skill.name] = entry

    # 4. ~/.agents/skills
    home_agents_dir = home_agents_skills_dir or (Path.home() / ".agents" / "skills")
    if home_agents_dir.exists():
        for entry in scan_skills_directory(home_agents_dir, source="workspace", context=context):
            by_name[entry.skill.name] = entry

    # 5. <workspace>/.agents/skills
    if workspace_agents_skills_dir:
        for entry in scan_skills_directory(workspace_agents_skills_dir, source="workspace", context=context):
            by_name[entry.skill.name] = entry

    # 6. <workspace>/skills
    if workspace_skills_dir:
        for entry in scan_skills_directory(workspace_skills_dir, source="workspace", context=context):
            by_name[entry.skill.name] = entry

    return list(by_name.values())


__all__ = ["discover_all_skills", "scan_skills_directory"]
