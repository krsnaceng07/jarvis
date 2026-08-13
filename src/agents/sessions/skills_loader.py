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

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, TypedDict

from .diagnostics import ResourceDiagnostic
from .source_info import create_synthetic_source_info
from src.frontmatter import split_skill_file


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


MAX_NAME_LENGTH = 64
MAX_DESCRIPTION_LENGTH = 1024


def _resolve_skill_path(path: str, cwd: str) -> str:
    normalized = os.path.expanduser(path)
    if os.path.isabs(normalized):
        return normalized
    return os.path.abspath(os.path.join(cwd, normalized))


def _is_under_path(target: str, root: str) -> bool:
    target_resolved = os.path.abspath(target)
    root_resolved = os.path.abspath(root)
    if target_resolved == root_resolved:
        return True
    root_with_sep = root_resolved if root_resolved.endswith(os.sep) else root_resolved + os.sep
    return target_resolved.startswith(root_with_sep)


def _validate_name(name: str) -> list[str]:
    errors: list[str] = []
    if len(name) > MAX_NAME_LENGTH:
        errors.append(f"name exceeds {MAX_NAME_LENGTH} characters ({len(name)})")
    if not re.fullmatch(r"[a-z0-9-]+", name):
        errors.append("name contains invalid characters (must be lowercase a-z, 0-9, hyphens only)")
    if name.startswith("-") or name.endswith("-"):
        errors.append("name must not start or end with a hyphen")
    if "--" in name:
        errors.append("name must not contain consecutive hyphens")
    return errors


def _validate_description(description: str) -> list[str]:
    errors: list[str] = []
    if not description or description.strip() == "":
        errors.append("description is required")
    elif len(description) > MAX_DESCRIPTION_LENGTH:
        errors.append(
            f"description exceeds {MAX_DESCRIPTION_LENGTH} characters ({len(description)})"
        )
    return errors


def _create_skill_source_info(file_path: str, base_dir: str, source: str) -> SkillSourceInfo:
    if source == "user":
        return create_synthetic_source_info(
            file_path,
            {
                "source": "local",
                "scope": "user",
                "origin": "top-level",
                "baseDir": base_dir,
            },
        )
    if source == "project":
        return create_synthetic_source_info(
            file_path,
            {
                "source": "local",
                "scope": "project",
                "origin": "top-level",
                "baseDir": base_dir,
            },
        )
    return create_synthetic_source_info(
        file_path,
        {
            "source": "local",
            "origin": "top-level",
            "baseDir": base_dir,
        },
    )


def _load_skill_from_file(
    file_path: str,
    source: str,
) -> tuple[Optional[Skill], list[ResourceDiagnostic]]:
    diagnostics: list[ResourceDiagnostic] = []
    parsed = split_skill_file(Path(file_path))
    if parsed is None:
        diagnostics.append(
            ResourceDiagnostic(
                type="warning",
                message="failed to read skill file",
                path=file_path,
            )
        )
        return None, diagnostics

    frontmatter, body = parsed
    name = str(frontmatter.get("name", Path(file_path).parent.name)).strip()
    description = str(frontmatter.get("description", "")).strip()
    for error in _validate_name(name):
        diagnostics.append(
            ResourceDiagnostic(type="warning", message=error, path=file_path)
        )
    for error in _validate_description(description):
        diagnostics.append(
            ResourceDiagnostic(type="warning", message=error, path=file_path)
        )

    if not description:
        return None, diagnostics

    disable_model_invocation = bool(
        frontmatter.get("disable-model-invocation", frontmatter.get("disableModelInvocation", False))
    )

    skill = Skill(
        name=name,
        description=description,
        file_path=file_path,
        base_dir=str(Path(file_path).parent),
        frontmatter=frontmatter,
        body=body,
        source_info=_create_skill_source_info(
            file_path, str(Path(file_path).parent), source
        ),
        disable_model_invocation=disable_model_invocation,
    )
    return skill, diagnostics


def _load_skills_from_dir_internal(
    dir_path: str,
    source: str,
    include_root_files: bool,
) -> LoadSkillsResult:
    skills: list[Skill] = []
    diagnostics: list[ResourceDiagnostic] = []
    if not os.path.isdir(dir_path):
        return {"skills": skills, "diagnostics": diagnostics}

    try:
        entries = sorted(os.listdir(dir_path))
    except OSError as exc:
        diagnostics.append(
            ResourceDiagnostic(
                type="warning",
                message=str(exc),
                path=dir_path,
            )
        )
        return {"skills": skills, "diagnostics": diagnostics}

    root_skill_path = os.path.join(dir_path, "SKILL.md")
    if "SKILL.md" in entries and os.path.isfile(root_skill_path):
        skill, skill_diagnostics = _load_skill_from_file(root_skill_path, source)
        diagnostics.extend(skill_diagnostics)
        if skill is not None:
            skills.append(skill)
        return {"skills": skills, "diagnostics": diagnostics}

    for entry_name in entries:
        if entry_name.startswith(".") or entry_name == "node_modules":
            continue
        full_path = os.path.join(dir_path, entry_name)
        if os.path.isdir(full_path):
            result = _load_skills_from_dir_internal(full_path, source, False)
            skills.extend(result["skills"])
            diagnostics.extend(result["diagnostics"])
            continue
        if not include_root_files or not entry_name.endswith(".md"):
            continue
        if not os.path.isfile(full_path):
            continue
        skill, skill_diagnostics = _load_skill_from_file(full_path, source)
        diagnostics.extend(skill_diagnostics)
        if skill is not None:
            skills.append(skill)

    return {"skills": skills, "diagnostics": diagnostics}


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
    (``skills/loading/session.js``)."""
    skill_paths = skill_paths or []
    all_diagnostics: list[ResourceDiagnostic] = []
    collision_diagnostics: list[ResourceDiagnostic] = []
    skill_map: dict[str, Skill] = {}
    real_path_set: set[str] = set()

    def add_skills(result: LoadSkillsResult) -> None:
        all_diagnostics.extend(result.get("diagnostics", []))
        for skill in result.get("skills", []):
            real_path = os.path.realpath(skill.file_path)
            if real_path in real_path_set:
                continue
            existing = skill_map.get(skill.name)
            if existing is not None:
                collision_diagnostics.append(
                    ResourceDiagnostic(
                        type="collision",
                        message=f'name "{skill.name}" collision',
                        path=skill.file_path,
                        collision=None,
                    )
                )
            else:
                skill_map[skill.name] = skill
                real_path_set.add(real_path)

    if include_defaults:
        add_skills(
            _load_skills_from_dir_internal(
                os.path.join(agent_dir, "skills"), "user", True
            )
        )
        add_skills(
            _load_skills_from_dir_internal(
                os.path.join(cwd, ".jarvis", "skills"), "project", True
            )
        )

    user_skills_dir = os.path.join(agent_dir, "skills")
    project_skills_dir = os.path.join(cwd, ".jarvis", "skills")

    def get_source(resolved_path: str) -> str:
        if not include_defaults:
            if _is_under_path(resolved_path, user_skills_dir):
                return "user"
            if _is_under_path(resolved_path, project_skills_dir):
                return "project"
        return "path"

    for raw_path in skill_paths:
        resolved_path = _resolve_skill_path(raw_path, cwd)
        if not os.path.exists(resolved_path):
            all_diagnostics.append(
                ResourceDiagnostic(
                    type="warning",
                    message="skill path does not exist",
                    path=resolved_path,
                )
            )
            continue

        if os.path.isdir(resolved_path):
            add_skills(
                _load_skills_from_dir_internal(
                    resolved_path, get_source(resolved_path), True
                )
            )
            continue

        if os.path.isfile(resolved_path) and resolved_path.endswith(".md"):
            skill, skill_diagnostics = _load_skill_from_file(
                resolved_path, get_source(resolved_path)
            )
            all_diagnostics.extend(skill_diagnostics)
            if skill is not None:
                add_skills({"skills": [skill], "diagnostics": []})
            continue

        all_diagnostics.append(
            ResourceDiagnostic(
                type="warning",
                message="skill path is not a markdown file",
                path=resolved_path,
            )
        )

    return {
        "skills": list(skill_map.values()),
        "diagnostics": all_diagnostics + collision_diagnostics,
    }


__all__ = [
    "LoadSkillsResult",
    "Skill",
    "SkillSourceInfo",
    "loadSkills",
]
