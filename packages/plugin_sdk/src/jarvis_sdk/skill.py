"""Skill types — declarative markdown tools.

Mirrors OpenClaw's ``skills/<name>/SKILL.md`` pattern. A skill is a
single markdown file with YAML frontmatter + a free-form body that
the LLM reads as part of the system prompt. Skills augment, they
don't replace, code-backed tools.

OpenClaw's canonical example is ``skills/weather/SKILL.md``::

    ---
    name: weather
    description: "Get current weather and forecasts (no API key needed)."
    metadata:
      { "openclaw": { "emoji": "🌤️" } }
    ---

    # Weather
    Use when the user asks about weather, temperature, rain...

The frontmatter keys we honor:

  - ``name`` (required) — kebab-case id.
  - ``description`` (required) — short "when to use" prompt the LLM sees.
  - ``metadata.openclaw.emoji`` (optional) — UI hint only.
  - ``metadata.openclaw.requires.bins`` (optional) — required CLI tools.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class SkillDecl:
    """A loaded skill's parsed declaration.

    Mirrors OpenClaw's parsed ``SKILL.md`` frontmatter. The body is
    included verbatim (the host injects it into the system prompt).
    """

    name: str
    description: str
    body: str
    emoji: str = ""
    requires_bins: tuple[str, ...] = ()
    raw_frontmatter: dict[str, Any] = field(default_factory=dict)
    source_path: str = ""


__all__ = ["SkillDecl"]
