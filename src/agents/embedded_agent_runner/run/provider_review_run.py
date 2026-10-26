"""jarvis.agents.embedded_agent_runner.run.provider_review_run — Provider review and precaution.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/provider-review-run.ts``.
"""

from __future__ import annotations

from typing import Any

from .types import EmbeddedRunAttemptResult


class ProviderReviewRun:
    def __init__(
        self,
        run: Any,
        runtime: Any,
        session: Any,
        assert_current: Any = None,
    ) -> None:
        self.run = run
        self.runtime = runtime
        self.session = session
        self.assert_current = assert_current
        params = getattr(run, "run_params", None)
        if isinstance(run, dict):
            params = run.get("run_params") or run.get("runParams")
        self.params = params or {}
        self.acknowledgment = self.params.get("providerReviewAcknowledgment")

    async def admit(self) -> None:
        if self.assert_current:
            self.assert_current()

    def begin_attempt(self) -> None:
        pass

    def failure(self, cause: Any = None) -> None:
        pass

    async def settle(self, attempt: Any) -> Any:
        # Check provider refusal / misalignment if present
        assistant = getattr(attempt, "currentAttemptCompletedAssistant", None) or getattr(
            attempt, "currentAttemptAssistant", None
        )
        if isinstance(attempt, dict):
            assistant = attempt.get("currentAttemptCompletedAssistant") or attempt.get("currentAttemptAssistant")

        stop_reason = None
        if isinstance(assistant, dict):
            stop_reason = assistant.get("stopReason")
        elif assistant is not None:
            stop_reason = getattr(assistant, "stopReason", None)

        if stop_reason == "refusal":
            return {"category": "misalignment"}
        return None

    def finish(self, result: Any) -> Any:
        return result


def create_provider_review_run(
    run: Any = None,
    runtime: Any = None,
    session: Any = None,
    assert_current: Any = None,
    **kwargs: Any,
) -> ProviderReviewRun:
    actual_run = run or kwargs.get("input", {}).get("run")
    actual_runtime = runtime or kwargs.get("input", {}).get("runtime")
    actual_session = session or kwargs.get("input", {}).get("session")
    actual_assert = assert_current or kwargs.get("input", {}).get("assertCurrent")
    return ProviderReviewRun(
        run=actual_run,
        runtime=actual_runtime,
        session=actual_session,
        assert_current=actual_assert,
    )


__all__ = ["create_provider_review_run", "ProviderReviewRun"]
