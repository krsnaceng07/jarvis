"""jarvis.agents.embedded_agent_runner.run.retry_budget — Run retry budget tracking.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/retry-budget.ts``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Sequence

RunRetryKind = Literal["progress_continuation", "recovery"]


@dataclass
class RunRetryBudget:
    attemptsDispatched: int = 0
    attemptsCounted: int = 0
    maxAttempts: int = 0


def create_run_retry_budget(max_attempts: int) -> RunRetryBudget:
    return RunRetryBudget(
        attemptsDispatched=0,
        attemptsCounted=0,
        maxAttempts=max_attempts,
    )


def is_run_retry_budget_exhausted(budget: RunRetryBudget) -> bool:
    return budget.attemptsCounted >= budget.maxAttempts


def begin_run_attempt(budget: RunRetryBudget) -> None:
    budget.attemptsDispatched += 1
    budget.attemptsCounted += 1


def record_run_model_progress(budget: RunRetryBudget) -> None:
    # Retain the current attempt's failed tail, not failures before a completed response.
    # Partial output and tool-only continuations do not replenish this guard.
    budget.attemptsCounted = 1


def resolve_run_retry_kind(
    preflight_recovery: dict[str, Any],
    retrying_from_transcript: bool,
    tool_metas: Sequence[dict[str, Any]],
) -> RunRetryKind:
    if (
        retrying_from_transcript
        and preflight_recovery.get("route") == "truncate_tool_results_only"
        and preflight_recovery.get("truncatedCount", 0) == 0
        and any(tool.get("isError") is not True for tool in tool_metas)
    ):
        return "progress_continuation"
    return "recovery"


def record_run_retry(budget: RunRetryBudget, kind: RunRetryKind) -> None:
    if kind == "progress_continuation":
        budget.attemptsCounted = max(0, budget.attemptsCounted - 1)


__all__ = [
    "RunRetryKind",
    "RunRetryBudget",
    "create_run_retry_budget",
    "is_run_retry_budget_exhausted",
    "begin_run_attempt",
    "record_run_model_progress",
    "resolve_run_retry_kind",
    "record_run_retry",
]
