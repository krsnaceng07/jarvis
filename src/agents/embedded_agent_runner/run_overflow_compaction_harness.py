"""jarvis.agents.embedded_agent_runner.run_overflow_compaction_harness — test harness for overflow compaction.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run.overflow-compaction.harness.ts``.

The original file is a vitest test harness exposing ``vi.fn()`` mocks for
overflow compaction, failover, and runtime-plan coverage. Python's equivalent
is a pytest fixture module, and the test logic lives in the matching
``tests/test_phase76h6_*_overflow_compaction.py`` tests. The companion
installable stubs here let the focused port expose the same public surface
without dragging in the full vitest mock runtime.

Public surface:

- :func:`reset_run_overflow_compaction_harness_mocks`
- :func:`load_run_overflow_compaction_harness`
- :func:`warm_run_overflow_compaction_harness`
- :func:`use_openai_platform_auth_fixture`
- :data:`run_overflow_compaction_test_api`
- :data:`overflow_base_run_params`

Phase 7.6h-6 — focused minimal port.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional


_run_overflow_compaction_harness_state: Dict[str, Any] = {
    "mockedGlobalHookRunner": {},
    "mockedContextEngine": {},
    "mockedCompactDirect": None,
    "mockedBuildAgentRuntimePlan": None,
    "mockedRunPostCompactionSideEffects": None,
    "mockedSleepWithAbort": None,
    "mockedEnsureRuntimePluginsLoaded": None,
    "mockedResolveModelAsync": None,
    "mockedRunEmbeddedAttempt": None,
    "mockedBuildEmbeddedRunPayloads": None,
    "mockedRunContextEngineMaintenance": None,
    "mockedWaitForDeferredTurnMaintenanceForSession": None,
    "mockedSessionLikelyHasOversizedToolResults": None,
    "mockedTruncateOversizedToolResultsInSession": None,
    "mockedCoerceToFailoverError": None,
    "mockedDescribeFailoverError": None,
    "mockedResolveFailoverStatus": None,
    "mockedClassifyFailoverReason": None,
    "mockedClassifyAssistantFailoverReason": None,
    "mockedExtractObservedOverflowTokenCount": None,
    "mockedFormatAssistantErrorText": None,
    "mockedIsCompactionFailureError": None,
    "mockedIsFailoverAssistantError": None,
    "mockedIsLikelyContextOverflowError": None,
    "mockedIsRateLimitAssistantError": None,
    "mockedPickFallbackThinkingLevel": None,
    "mockedEvaluateContextWindowGuard": None,
    "mockedResolveContextWindowInfo": None,
    "mockedGetApiKeyForModel": None,
    "mockedIsProfileInCooldown": None,
    "mockedMarkAuthProfileFailure": None,
    "mockedEnsureAuthProfileStore": None,
    "mockedEnsureAuthProfileStoreWithoutExternalProfiles": None,
    "mockedResolveAuthProfileOrder": None,
    "mockedResolveProviderEntryApiKeyProfileReference": None,
    "mockedMarkAuthProfileSuccess": None,
}


#: Default base run params for overflow-compaction tests.
overflow_base_run_params: Dict[str, Any] = {
    "prompt": "test prompt",
    "sessionKey": "test-session",
    "workspaceDir": "/tmp/workspace",
    "agentId": "main",
    "provider": "openai",
    "modelId": "gpt-5",
}


# Installable hooks ---------------------------------------------------------

_run_overflow_compaction_harness_hook = None
_set_run_overflow_compaction_harness_mocks_hook = None


def set_run_overflow_compaction_harness_hook(fn) -> None:
    global _run_overflow_compaction_harness_hook
    _run_overflow_compaction_harness_hook = fn


def set_run_overflow_compaction_harness_mocks_hook(fn) -> None:
    global _set_run_overflow_compaction_harness_mocks_hook
    _set_run_overflow_compaction_harness_mocks_hook = fn


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def use_openai_platform_auth_fixture() -> None:
    """Install the OpenAI platform-auth fixture for overflow-compaction tests.

    Mirrors :func:`useOpenAIPlatformAuthFixture`
    (``run.overflow-compaction.harness.ts``).
    """
    if _set_run_overflow_compaction_harness_mocks_hook is not None:
        _set_run_overflow_compaction_harness_mocks_hook({"op": "useOpenAIPlatformAuthFixture"})


def reset_run_overflow_compaction_harness_mocks() -> None:
    """Reset all overflow-compaction harness mocks to defaults.

    Mirrors :func:`resetRunOverflowCompactionHarnessMocks`
    (``run.overflow-compaction.harness.ts``).
    """
    if _set_run_overflow_compaction_harness_mocks_hook is not None:
        _set_run_overflow_compaction_harness_mocks_hook({"op": "resetAll"})
        return
    for key in list(_run_overflow_compaction_harness_state.keys()):
        _run_overflow_compaction_harness_state[key] = None
    _run_overflow_compaction_harness_state["mockedGlobalHookRunner"] = {}


async def load_run_overflow_compaction_harness() -> Dict[str, Any]:
    """Load the overflow-compaction harness and return its installed mocks.

    Mirrors :func:`loadRunOverflowCompactionHarness`
    (``run.overflow-compaction.harness.ts``).
    """
    if _run_overflow_compaction_harness_hook is not None:
        v = _run_overflow_compaction_harness_hook({"op": "load"})
        if hasattr(v, "__await__"):
            return await v  # type: ignore[func-returns-value]
        return v or dict(_run_overflow_compaction_harness_state)
    return dict(_run_overflow_compaction_harness_state)


async def warm_run_overflow_compaction_harness() -> Dict[str, Any]:
    """Warm the overflow-compaction harness and return its installed mocks.

    Mirrors :func:`warmRunOverflowCompactionHarness`
    (``run.overflow-compaction.harness.ts``).
    """
    if _run_overflow_compaction_harness_hook is not None:
        v = _run_overflow_compaction_harness_hook({"op": "warm"})
        if hasattr(v, "__await__"):
            return await v  # type: ignore[func-returns-value]
        return v or dict(_run_overflow_compaction_harness_state)
    return dict(_run_overflow_compaction_harness_state)


#: Test-only API surface mirroring the OpenClaw harness global.
run_overflow_compaction_test_api: Dict[str, Any] = {
    "useOpenAIPlatformAuthFixture": use_openai_platform_auth_fixture,
    "resetRunOverflowCompactionHarnessMocks": reset_run_overflow_compaction_harness_mocks,
    "loadRunOverflowCompactionHarness": load_run_overflow_compaction_harness,
    "warmRunOverflowCompactionHarness": warm_run_overflow_compaction_harness,
    "overflowBaseRunParams": overflow_base_run_params,
}


__all__ = [
    "overflow_base_run_params",
    "use_openai_platform_auth_fixture",
    "reset_run_overflow_compaction_harness_mocks",
    "load_run_overflow_compaction_harness",
    "warm_run_overflow_compaction_harness",
    "run_overflow_compaction_test_api",
    "set_run_overflow_compaction_harness_hook",
    "set_run_overflow_compaction_harness_mocks_hook",
]
