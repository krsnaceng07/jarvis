"""Skill loader — mirrors OpenClaw ``src/skills/loading/``.

Parses SKILL.md YAML frontmatter and creates validated ``SkillEntry`` objects.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from src.frontmatter import split_skill_file
from ..types import (
    Skill,
    SkillEntry,
    SkillExposure,
    SkillInstallSpec,
    SkillInvocationPolicy,
    SkillMetadata,
    SkillTelemetrySource,
)

_log = logging.getLogger("jarvis.skills.loader")


def _parse_install_spec(raw: dict[str, Any]) -> SkillInstallSpec | None:
    kind = raw.get("kind")
    if kind not in ("brew", "node", "go", "uv", "download"):
        return None
    bins = tuple(raw.get("bins") or [])
    os_tuple = tuple(raw.get("os") or [])
    return SkillInstallSpec(
        kind=kind,
        label=raw.get("label"),
        bins=bins,
        os=os_tuple,
        formula=raw.get("formula"),
        package=raw.get("package"),
        module=raw.get("module"),
        url=raw.get("url"),
        archive=raw.get("archive"),
        extract=bool(raw.get("extract", False)),
        target_dir=raw.get("target_dir"),
    )


def load_skill_from_dir(
    skill_dir: Path,
    source: SkillTelemetrySource = "bundled",
    plugin_id: str | None = None,
) -> SkillEntry | None:
    """Load and parse SKILL.md in skill_dir. Returns None if invalid or missing."""
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.is_file():
        return None

    parsed = split_skill_file(skill_md)
    if parsed is None:
        return None

    fm, body = parsed
    name = str(fm.get("name", skill_dir.name)).strip()
    description = str(fm.get("description", "")).strip()
    if not name or not description:
        _log.warning("skills: %s missing name/description", skill_md)
        return None

    # Parse openclaw/jarvis metadata section if present
    meta_dict = fm.get("metadata") or {}
    oc_meta = meta_dict.get("openclaw") or meta_dict.get("jarvis") or {}
    reqs = oc_meta.get("requires") or fm.get("requires") or {}

    installs: list[SkillInstallSpec] = []
    for inst_raw in oc_meta.get("install") or []:
        if isinstance(inst_raw, dict):
            spec = _parse_install_spec(inst_raw)
            if spec:
                installs.append(spec)

    metadata = SkillMetadata(
        always=bool(fm.get("always") or oc_meta.get("always", False)),
        skill_key=fm.get("skill_key") or oc_meta.get("skillKey"),
        primary_env=oc_meta.get("primaryEnv"),
        emoji=str(oc_meta.get("emoji") or fm.get("emoji") or "").strip() or None,
        homepage=oc_meta.get("homepage"),
        os=tuple(oc_meta.get("os") or []),
        requires_bins=tuple(reqs.get("bins") or []),
        requires_any_bins=tuple(reqs.get("anyBins") or []),
        requires_env=tuple(reqs.get("env") or []),
        requires_config=tuple(reqs.get("config") or []),
        install=tuple(installs),
    )

    invoc = SkillInvocationPolicy(
        user_invocable=bool(fm.get("userInvocable", True)),
        disable_model_invocation=bool(fm.get("disableModelInvocation", False)),
    )

    exposure = SkillExposure(
        include_in_runtime_registry=True,
        include_in_available_skills_prompt=not metadata.always,
        user_invocable=invoc.user_invocable,
    )

    skill = Skill(
        name=name,
        description=description,
        body=body.strip(),
        skill_file=str(skill_md),
        base_dir=str(skill_dir),
        source=source,
        plugin_id=plugin_id,
    )

    return SkillEntry(
        skill=skill,
        frontmatter={str(k): str(v) for k, v in fm.items()},
        metadata=metadata,
        invocation=invoc,
        exposure=exposure,
    )


__all__ = ["load_skill_from_dir"]
