"""Skill security validator — mirrors OpenClaw ``src/skills/security/``.

Enforces path containment (preventing symlink path traversal out of skill root)
and validates execution eligibility.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..types import SkillEntry, SkillEligibilityContext


def validate_skill_path_containment(skill_dir: str, candidate_path: str) -> bool:
    """Check if candidate_path is safely contained within skill_dir using realpath."""
    try:
        real_root = os.path.realpath(skill_dir)
        real_candidate = os.path.realpath(candidate_path)
        return real_candidate == real_root or real_candidate.startswith(real_root + os.sep)
    except OSError:
        return False


def validate_skill_eligibility(
    entry: SkillEntry,
    context: SkillEligibilityContext | None = None,
) -> bool:
    """Validate whether a skill's requirements are satisfied in context.

    Checks required OS, required bins, required anyBins, and required env.
    """
    if entry.metadata is None:
        return True

    meta = entry.metadata
    if context is None:
        return True

    # OS check
    if meta.os and context.platform not in meta.os:
        return False

    # required bins (all must be present)
    for b in meta.requires_bins:
        if not context.has_bin(b):
            return False

    # required anyBins (at least one must be present)
    if meta.requires_any_bins and not context.has_any_bin(list(meta.requires_any_bins)):
        return False

    # required env
    for e in meta.requires_env:
        if not context.has_env(e):
            return False

    return True


__all__ = ["validate_skill_path_containment", "validate_skill_eligibility"]
