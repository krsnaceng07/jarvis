"""jarvis.skills.skill_loading — Skill loading order, precedence hierarchy & discovery.

OpenClaw parity: mirrors
``openclaw-main/docs/tools/skills.md`` and
``openclaw-main/src/skills/loading/config.ts``.

Precedence hierarchy (highest precedence first):
1. Workspace skills: `<workspace>/skills`
2. Project agent skills: `<workspace>/.agents/skills`
3. Personal agent skills: `~/.agents/skills`
4. Managed / local skills: `<state-dir>/skills`
5. Bundled skills: shipped with install
6. Extra directories: `skills.load.extraDirs` + plugin skills

Features:
- `SkillSourcePrecedence`: Priority level enum (1 to 6).
- `SkillMetadata`: Frontmatter metadata dataclass.
- `SkillDescriptor`: Full skill descriptor dataclass.
- `resolve_skill_discovery_hierarchy()`: Resolves ordered skill discovery root directories.
- `evaluate_skill_eligibility()`: Evaluates skill gating rules (OS, binaries, env, config).
- `filter_agent_skills()`: Applies per-agent skill allowlists.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from enum import IntEnum
from pathlib import Path
from typing import Any, Literal


class SkillSourcePrecedence(IntEnum):
    WORKSPACE = 1
    PROJECT_AGENT = 2
    PERSONAL_AGENT = 3
    MANAGED = 4
    BUNDLED = 5
    EXTRA_DIR = 6


@dataclass
class SkillMetadata:
    name: str
    description: str
    homepage: str | None = None
    user_invocable: bool = True
    disable_model_invocation: bool = False
    command_dispatch: Literal["tool"] | None = None
    command_tool: str | None = None
    command_arg_mode: str = "raw"
    requires_bins: list[str] = field(default_factory=list)
    requires_any_bins: list[str] = field(default_factory=list)
    requires_env: list[str] = field(default_factory=list)
    requires_config: list[str] = field(default_factory=list)
    os_target: list[str] = field(default_factory=list)


@dataclass
class SkillDescriptor:
    id: str
    name: str
    description: str
    skill_path: str
    precedence: SkillSourcePrecedence
    metadata: SkillMetadata
    enabled: bool = True


def resolve_skill_discovery_hierarchy(
    workspace_dir: str | None = None,
    state_dir: str | None = None,
    extra_dirs: list[str] | None = None,
) -> list[tuple[SkillSourcePrecedence, str]]:
    """Resolve ordered skill root directories by precedence (highest first)."""
    roots: list[tuple[SkillSourcePrecedence, str]] = []

    ws = Path(workspace_dir).resolve() if workspace_dir else Path.cwd().resolve()
    state = Path(state_dir).resolve() if state_dir else (Path.home() / ".jarvis")

    # 1. Workspace skills
    roots.append((SkillSourcePrecedence.WORKSPACE, str(ws / "skills")))
    # 2. Project agent skills
    roots.append((SkillSourcePrecedence.PROJECT_AGENT, str(ws / ".agents" / "skills")))
    # 3. Personal agent skills
    roots.append((SkillSourcePrecedence.PERSONAL_AGENT, str(Path.home() / ".agents" / "skills")))
    # 4. Managed skills
    roots.append((SkillSourcePrecedence.MANAGED, str(state / "skills")))
    # 5. Bundled skills
    bundled_path = Path(__file__).parent.parent.parent / "skills"
    roots.append((SkillSourcePrecedence.BUNDLED, str(bundled_path)))
    # 6. Extra dirs
    if extra_dirs:
        for ed in extra_dirs:
            roots.append((SkillSourcePrecedence.EXTRA_DIR, str(Path(ed).resolve())))

    return roots


def evaluate_skill_eligibility(metadata: SkillMetadata, config: dict[str, Any] | None = None) -> bool:
    """Evaluate whether a skill is eligible based on OS, binaries, env, and config."""
    # OS filter
    if metadata.os_target:
        current_os = sys.platform  # e.g., 'win32', 'darwin', 'linux'
        if current_os not in metadata.os_target:
            return False

    # Required binaries
    for bin_name in metadata.requires_bins:
        if not any(
            (Path(path_dir) / bin_name).exists() or (Path(path_dir) / f"{bin_name}.exe").exists()
            for path_dir in os.environ.get("PATH", "").split(os.pathsep)
            if path_dir
        ):
            return False

    # Required env vars
    for env_var in metadata.requires_env:
        if env_var not in os.environ:
            return False

    return True


def filter_agent_skills(
    skills: list[SkillDescriptor],
    agent_id: str,
    config: dict[str, Any] | None = None,
) -> list[SkillDescriptor]:
    """Filter effective skills for a specific agent using allowlists."""
    cfg = config or {}
    agents_cfg = cfg.get("agents", {})
    defaults_allowlist = agents_cfg.get("defaults", {}).get("skills")

    entries = agents_cfg.get("entries", {})
    agent_entry = entries.get(agent_id, {})
    agent_allowlist = agent_entry.get("skills")

    # If agent entry explicitly specifies skills, that is the authoritative list
    effective_allowlist = agent_allowlist if agent_allowlist is not None else defaults_allowlist

    if effective_allowlist is None:
        return [s for s in skills if s.enabled]

    allow_set = set(effective_allowlist)
    return [s for s in skills if s.enabled and s.name in allow_set]


__all__ = [
    "SkillDescriptor",
    "SkillMetadata",
    "SkillSourcePrecedence",
    "evaluate_skill_eligibility",
    "filter_agent_skills",
    "resolve_skill_discovery_hierarchy",
]
