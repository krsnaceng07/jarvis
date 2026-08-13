"""Skill type definitions — mirrors OpenClaw ``src/skills/types.ts``."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Any

SkillTelemetrySource = Literal["bundled", "unknown", "workspace", "plugin"]

@dataclass(frozen=True, slots=True)
class SkillInstallSpec:
    kind: Literal["brew", "node", "go", "uv", "download"]
    label: str | None = None
    bins: tuple[str, ...] = field(default_factory=tuple)
    os: tuple[str, ...] = field(default_factory=tuple)
    formula: str | None = None
    package: str | None = None
    module: str | None = None
    url: str | None = None
    archive: str | None = None
    extract: bool = False
    target_dir: str | None = None


@dataclass(frozen=True, slots=True)
class SkillMetadata:
    always: bool = False
    skill_key: str | None = None
    primary_env: str | None = None
    emoji: str | None = None
    homepage: str | None = None
    os: tuple[str, ...] = field(default_factory=tuple)
    requires_bins: tuple[str, ...] = field(default_factory=tuple)
    requires_any_bins: tuple[str, ...] = field(default_factory=tuple)
    requires_env: tuple[str, ...] = field(default_factory=tuple)
    requires_config: tuple[str, ...] = field(default_factory=tuple)
    install: tuple[SkillInstallSpec, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class SkillInvocationPolicy:
    user_invocable: bool = True
    disable_model_invocation: bool = False


@dataclass(frozen=True, slots=True)
class SkillExposure:
    include_in_runtime_registry: bool = True
    include_in_available_skills_prompt: bool = True
    user_invocable: bool = True


@dataclass(frozen=True, slots=True)
class Skill:
    name: str
    description: str
    body: str
    skill_file: str          # Path to SKILL.md
    base_dir: str            # Directory containing SKILL.md
    source: SkillTelemetrySource = "bundled"
    plugin_id: str | None = None


@dataclass
class SkillEntry:
    skill: Skill
    frontmatter: dict[str, Any]
    metadata: SkillMetadata | None = None
    invocation: SkillInvocationPolicy | None = None
    exposure: SkillExposure | None = None
    disable_command_dispatch: bool = False


@dataclass
class SkillEligibilityContext:
    platform: str = "windows"
    has_bins: frozenset[str] = field(default_factory=frozenset)
    env_vars: frozenset[str] = field(default_factory=frozenset)

    def has_bin(self, name: str) -> bool:
        return name in self.has_bins

    def has_any_bin(self, names: list[str]) -> bool:
        return any(b in self.has_bins for b in names)

    def has_env(self, name: str) -> bool:
        return name in self.env_vars


@dataclass
class SkillSnapshot:
    prompt: str
    skills: list[dict[str, Any]]
    resolved_skills: list[Skill] = field(default_factory=list)
    version: int = 3


__all__ = [
    "Skill",
    "SkillEligibilityContext",
    "SkillEntry",
    "SkillExposure",
    "SkillInstallSpec",
    "SkillInvocationPolicy",
    "SkillMetadata",
    "SkillSnapshot",
    "SkillTelemetrySource",
]
