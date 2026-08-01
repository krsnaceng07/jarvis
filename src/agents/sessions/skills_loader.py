"""jarvis.agents.sessions.skills_loader — skill loading (stub).

OpenClaw parity: mirrors the public surface
of ``openclaw-main/src/skills/loading/session.js``:

- :class:`Skill` — a single loaded skill
  (the OpenClaw source's ``Skill`` type).
- :func:`loadSkills` — entry point that
  returns ``{ skills, diagnostics }``.

The full skill loader (parse SKILL.md
front-matter, walk the project's
``.jarvis/skills/`` + ``.agents/skills/``
directories, dedupe by name) lands in
Phase 6.12+. The stub returns an empty
list so the resource loader can wire up
the public surface end-to-end without
pulling in the full skill pipeline.

Phase 6.11b — focused port.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, TypedDict

from .diagnostics import ResourceDiagnostic


class SkillSourceInfo(TypedDict, total=False):
    """Where a skill came from. Mirrors the
    ``sourceInfo`` field on
    :class:`Skill` (``skills/loading/session.js``)."""

    path: str
    source: str  # "local" | "npm:..." | "git:..." | "cli" | "auto"
    scope: str  # "user" | "project" | "temporary"
    origin: str  # "top-level" | "package"
    baseDir: Optional[str]


@dataclass
class Skill:
    """A single loaded skill. Mirrors
    ``Skill`` (``skills/loading/session.js``).

    Attributes
    ----------
    name : str
        The skill's identifier (from the
        ``name:`` front-matter field).
    description : str
        Human-readable description.
    file_path : str
        Filesystem path of the ``SKILL.md``
        (or ``.md`` for top-level skills).
    base_dir : str | None
        The skill's root dir (used for
        resolving relative paths inside the
        skill body).
    frontmatter : dict
        Parsed YAML front-matter.
    body : str
        Markdown body after the front-matter
        block.
    source_info : SkillSourceInfo | None
        Provenance info; populated by the
        resource loader.
    disable_model_invocation : bool
        When True, the model cannot call the
        skill itself (OpenClaw parity —
        ``disable-model-invocation``).
    """

    name: str
    description: str
    file_path: str
    base_dir: Optional[str] = None
    frontmatter: dict = field(default_factory=dict)
    body: str = ""
    source_info: Optional[SkillSourceInfo] = None
    disable_model_invocation: bool = False


class LoadSkillsResult(TypedDict, total=False):
    """Result of loading skills. Mirrors
    the return shape of ``loadSkills``
    (``skills/loading/session.js``)."""

    skills: list[Skill]
    diagnostics: list[ResourceDiagnostic]


def loadSkills(
    cwd: str,
    agent_dir: str,
    skill_paths: Optional[list[str]] = None,
    include_defaults: bool = True,
) -> LoadSkillsResult:
    """Load skills from the project's
    ``.jarvis/skills/`` + the agent's
    ``skills/`` + the supplied
    ``skill_paths``. Mirrors ``loadSkills``
    (``skills/loading/session.js``).

    Phase 6.11b — STUB. Returns an empty
    list of skills. The full loader
    (front-matter parsing, ancestor walk,
    name dedupe, source-info attachment)
    lands in Phase 6.12+.
    """
    return {"skills": [], "diagnostics": []}


__all__ = [
    "LoadSkillsResult",
    "Skill",
    "SkillSourceInfo",
    "loadSkills",
]
