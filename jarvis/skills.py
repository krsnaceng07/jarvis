"""Skills loader + registry — mirrors OpenClaw's `skills/` system.

A skill is a single ``SKILL.md`` file with YAML frontmatter + a
free-form body that the LLM reads as part of the system prompt.
Skills augment, they don't replace, code-backed tools.

OpenClaw's canonical example is ``skills/weather/SKILL.md``::

    ---
    name: weather
    description: "Get current weather and forecasts (no API key needed)."
    metadata: { "openclaw": { "emoji": "🌤️" } }
    ---

    # Weather
    Use when the user asks about weather, temperature, rain...

    ## Quick start
    ...
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from pathlib import Path

from jarvis_sdk import SkillDecl

from .frontmatter import split_skill_file

_log = logging.getLogger("jarvis.skills")


def discover_skills(skills_dir: Path) -> list[SkillDecl]:
    """Discover and parse every ``<skills_dir>/<name>/SKILL.md`` file.

    Mirrors OpenClaw's skills loader. Each subdirectory of
    ``skills_dir`` is expected to contain a ``SKILL.md`` with valid
    frontmatter. Invalid skills are logged and skipped (we never
    raise on a single bad skill — we want partial success).
    """
    if not skills_dir.exists():
        return []

    skills: list[SkillDecl] = []
    for entry in sorted(skills_dir.iterdir()):
        if not entry.is_dir():
            continue
        skill_md = entry / "SKILL.md"
        if not skill_md.is_file():
            continue
        try:
            skill = parse_skill(skill_md)
        except Exception as e:
            _log.warning("skills: failed to parse %s: %s", skill_md, e)
            continue
        if skill is not None:
            skills.append(skill)
    return skills


def parse_skill(skill_md: Path) -> SkillDecl | None:
    """Parse one ``SKILL.md`` into a ``SkillDecl``.

    Returns ``None`` if the file is missing ``name`` or ``description``.
    """
    parsed = split_skill_file(skill_md)
    if parsed is None:
        return None
    fm, body = parsed
    name = str(fm.get("name", "")).strip()
    description = str(fm.get("description", "")).strip()
    if not name or not description:
        _log.warning("skills: %s missing name/description", skill_md)
        return None

    metadata: dict[str, object] = cast("dict[str, object]", fm.get("metadata") or {})
    openclaw_meta: dict[str, object] = (
        cast("dict[str, object]", metadata.get("openclaw", {}))
        if isinstance(metadata, dict)
        else {}
    )
    requires: dict[str, object] = (
        cast("dict[str, object]", openclaw_meta.get("requires", {}))
        if isinstance(openclaw_meta, dict)
        else {}
    )
    bins_raw: object = requires.get("bins", []) if isinstance(requires, dict) else []
    bins: list[object] = list(cast("list[object]", bins_raw)) if isinstance(bins_raw, list) else []
    emoji = str(openclaw_meta.get("emoji", "")).strip() if isinstance(openclaw_meta, dict) else ""

    return SkillDecl(
        name=name,
        description=description,
        body=body.strip(),
        emoji=emoji,
        requires_bins=tuple(str(b) for b in bins),
        raw_frontmatter=fm,
        source_path=str(skill_md),
    )


def skills_to_prompt_section(skills: list[SkillDecl]) -> str:
    """Render a list of skills as a system-prompt section.

    Mirrors the way OpenClaw injects skills into the system prompt:
    each skill's name + description + body becomes a block. The
    description drives the LLM's "when to use" decision; the body
    is the reference card.
    """
    if not skills:
        return ""
    parts = ["# Skills\n"]
    for s in skills:
        parts.append(f"## {s.emoji} {s.name}\n" if s.emoji else f"## {s.name}\n")
        parts.append(f"{s.description}\n")
        if s.body:
            parts.append(f"{s.body}\n")
        parts.append("")  # blank line between skills
    return "\n".join(parts).strip()


__all__ = [
    "discover_skills",
    "parse_skill",
    "skills_to_prompt_section",
]
