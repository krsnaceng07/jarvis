"""Tests for src/skills/self_learning.py.

Mirrors tests of docs/tools/self-learning.md and src/skills/workshop/experience-review.ts in OpenClaw.
"""

from __future__ import annotations


from src.skills.self_learning import (
    ExperienceReviewContext,
    is_experience_review_eligible,
    resolve_autonomous_mode,
)


def test_resolve_autonomous_mode_default():
    assert resolve_autonomous_mode(None) == "auto"


def test_resolve_autonomous_mode_custom():
    cfg = {"skills": {"workshop": {"autonomous": {"mode": "propose"}}}}
    assert resolve_autonomous_mode(cfg) == "propose"


def test_is_experience_review_eligible_success():
    ctx = ExperienceReviewContext(
        modelIterations=12,
        trigger="user",
        skillWorkshopAvailable=True,
        endedInError=False,
    )
    assert is_experience_review_eligible(ctx) is True


def test_is_experience_review_eligible_ineligible():
    # 1. Less than 10 model iterations
    ctx1 = ExperienceReviewContext(modelIterations=5)
    assert is_experience_review_eligible(ctx1) is False

    # 2. Blocked trigger (cron)
    ctx2 = ExperienceReviewContext(modelIterations=15, trigger="cron")
    assert is_experience_review_eligible(ctx2) is False

    # 3. Mode off
    ctx3 = ExperienceReviewContext(modelIterations=15)
    cfg_off = {"skills": {"workshop": {"autonomous": {"mode": "off"}}}}
    assert is_experience_review_eligible(ctx3, cfg_off) is False
