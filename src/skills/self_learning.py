"""jarvis.skills.self_learning — Self-learning turns & autonomous experience review.

OpenClaw parity: mirrors
``openclaw-main/docs/tools/self-learning.md`` and
``openclaw-main/src/skills/workshop/experience-review.ts``.

Features:
- `AutonomousMode`: `"auto"` (default) | `"propose"` | `"off"`
- `EXPERIENCE_REVIEW_MIN_MODEL_ITERATIONS`: 10
- `EXPERIENCE_REVIEW_IDLE_MS`: 30000 (30s)
- `EXPERIENCE_REVIEW_TIMEOUT_MS`: 120000 (120s)
- `is_experience_review_eligible()`: Checks turn eligibility criteria.
- `resolve_autonomous_mode()`: Resolves current mode setting from config.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

AutonomousMode = Literal["auto", "propose", "off"]

EXPERIENCE_REVIEW_MIN_MODEL_ITERATIONS = 10
EXPERIENCE_REVIEW_IDLE_MS = 30000
EXPERIENCE_REVIEW_TIMEOUT_MS = 120000

BLOCKED_TRIGGERS: set[str] = {"cron", "heartbeat", "memory", "overflow", "hook", "subagent"}


@dataclass
class ExperienceReviewContext:
    agentId: str = "default"
    modelIterations: int = 0
    trigger: str = "user"
    skillWorkshopAvailable: bool = True
    endedInError: bool = False


def resolve_autonomous_mode(config: dict[str, Any] | None = None) -> AutonomousMode:
    """Resolve autonomous self-learning mode from config."""
    cfg = config or {}
    mode_raw = (
        cfg.get("skills", {})
        .get("workshop", {})
        .get("autonomous", {})
        .get("mode", "auto")
    )
    clean_mode = str(mode_raw).lower()
    if clean_mode in ("auto", "propose", "off"):
        return clean_mode  # type: ignore[return-value]
    return "auto"


def is_experience_review_eligible(
    ctx: ExperienceReviewContext,
    config: dict[str, Any] | None = None,
) -> bool:
    """Evaluate whether an agent turn is eligible for autonomous experience review."""
    mode = resolve_autonomous_mode(config)
    if mode == "off":
        return False

    if ctx.endedInError:
        return False

    if ctx.trigger in BLOCKED_TRIGGERS:
        return False

    if ctx.modelIterations < EXPERIENCE_REVIEW_MIN_MODEL_ITERATIONS:
        return False

    if not ctx.skillWorkshopAvailable:
        return False

    return True


__all__ = [
    "BLOCKED_TRIGGERS",
    "EXPERIENCE_REVIEW_IDLE_MS",
    "EXPERIENCE_REVIEW_MIN_MODEL_ITERATIONS",
    "EXPERIENCE_REVIEW_TIMEOUT_MS",
    "AutonomousMode",
    "ExperienceReviewContext",
    "is_experience_review_eligible",
    "resolve_autonomous_mode",
]
