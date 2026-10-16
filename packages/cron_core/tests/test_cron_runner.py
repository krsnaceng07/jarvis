"""Tests for jarvis_cron_core runner."""

from __future__ import annotations

from jarvis_cron_core.runner import CronRunner
from jarvis_cron_core.types import CronDecl


def test_cron_runner_add_remove() -> None:
    runner = CronRunner()
    fired = []

    def handler() -> None:
        fired.append(1)

    decl = CronDecl(
        id="test_job",
        schedule="*/5 * * * *",
        handler=handler,
    )

    runner.add(decl)
    assert len(runner.list()) == 1
    assert runner.list()[0].id == "test_job"

    runner.remove("test_job")
    assert len(runner.list()) == 0
