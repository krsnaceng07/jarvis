"""jarvis.config.types_skills — skill discovery/install/limits config types.

OpenClaw parity: mirrors ``openclaw-main/src/config/types.skills.ts``.
"""
from __future__ import annotations

from typing import Literal, TypedDict

#: Skill node-manager preference.
SkillsNodeManager = Literal["npm", "pnpm", "yarn", "bun"]


class SkillConfig(TypedDict, total=False):
    """Per-skill runtime override."""

    enabled: bool
    apiKey: object
    env: dict
    config: dict


class SkillsLoadConfig(TypedDict, total=False):
    extraDirs: list
    allowSymlinkTargets: list
    watch: bool
    watchDebounceMs: int


class SkillsInstallConfig(TypedDict, total=False):
    preferBrew: bool
    nodeManager: str
    allowUploadedArchives: bool


class SkillsLimitsConfig(TypedDict, total=False):
    maxCandidatesPerRoot: int
    maxSkillsLoadedPerSource: int
    maxSkillsInPrompt: int
    maxSkillsPromptChars: int
    maxSkillFileBytes: int


class SkillsWorkshopAutonomousConfig(TypedDict, total=False):
    enabled: bool


class SkillsWorkshopConfig(TypedDict, total=False):
    autonomous: SkillsWorkshopAutonomousConfig
    allowSymlinkTargetWrites: bool
    approvalPolicy: str
    maxPending: int
    maxSkillBytes: int


class SkillsConfig(TypedDict, total=False):
    allowBundled: list
    load: SkillsLoadConfig
    install: SkillsInstallConfig
    limits: SkillsLimitsConfig
    workshop: SkillsWorkshopConfig
    entries: dict


__all__ = [
    "SkillsNodeManager",
    "SkillConfig",
    "SkillsLoadConfig",
    "SkillsInstallConfig",
    "SkillsLimitsConfig",
    "SkillsWorkshopAutonomousConfig",
    "SkillsWorkshopConfig",
    "SkillsConfig",
]
