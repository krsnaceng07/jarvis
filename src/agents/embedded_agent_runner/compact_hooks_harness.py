"""jarvis.agents.embedded_agent_runner.compact_hooks_harness — test harness for compact/hooks tests.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/compact.hooks.harness.ts``.

The original file is a vitest test harness exposing ``vi.fn()`` mocks for the
compact and hook runtime. Python's equivalent is a pytest fixture module, and
the test logic lives in the matching ``tests/test_phase76h6_*_compact_hooks.py``
tests. The companion installable stubs here let the focused port expose the
same public surface without dragging in the full vitest mock runtime.

Public surface:

- :func:`reset_compact_hooks_harness_mocks`
- :func:`reset_compact_session_state_mocks`
- :func:`load_compact_hooks_harness`
- :func:`warm_compact_hooks_harness`
- :data:`compact_hooks_test_api`

Phase 7.6h-6 — focused minimal port.
"""
from __future__ import annotations

from typing import Any, Dict


_compact_hooks_harness_state: Dict[str, Any] = {
    "contextEngineCompactMock": None,
    "hookRunner": {},
    "ensureRuntimePluginsLoaded": None,
    "acquireSessionWriteLockMock": None,
    "resolveContextEngineMock": None,
    "resolveModelMock": None,
    "resolveModelAsyncMock": None,
    "sessionCompactImpl": None,
    "triggerInternalHook": None,
    "getMemorySearchManagerMock": None,
    "resolveMemorySearchConfigMock": None,
    "resolveSessionAgentIdMock": None,
    "resolveSessionAgentIdsMock": None,
    "estimateTokensMock": None,
    "resolveAgentHarnessPolicyMock": None,
    "selectAgentHarnessMock": None,
    "selectAgentHarnessForPreparedModelProvidersMock": None,
    "resolveContextWindowInfoMock": None,
    "sessionMessages": [],
    "sessionAbortCompactionMock": None,
    "createAgentSessionMock": None,
    "createOpenClawCodingToolsMock": None,
    "guardSessionManagerMock": None,
    "applyAgentCompactionSettingsFromConfigMock": None,
    "createPreparedEmbeddedAgentSettingsManagerMock": None,
    "listRegisteredPluginAgentPromptGuidanceMock": None,
    "buildEmbeddedSystemPromptMock": None,
    "resolveEmbeddedAgentStreamFnMock": None,
    "getApiKeyForModelMock": None,
    "resolveProviderEntryApiKeyProfileReferenceMock": None,
    "shouldPreferExplicitConfigApiKeyAuthMock": None,
    "registerProviderStreamForModelMock": None,
    "applyExtraParamsToAgentMock": None,
    "ensureAuthProfileStoreMock": None,
    "resolveSandboxContextMock": None,
    "maybeCompactAgentHarnessSessionMock": None,
    "compactWithSafetyTimeoutMock": None,
    "rotateTranscriptAfterCompactionMock": None,
    "enqueueCommandInLaneMock": None,
    "buildAgentRuntimePlanMock": None,
}


# Installable hooks ---------------------------------------------------------

_compact_hooks_harness_hook = None
_set_compact_hooks_harness_mocks_hook = None


def set_compact_hooks_harness_hook(fn) -> None:
    global _compact_hooks_harness_hook
    _compact_hooks_harness_hook = fn


def set_compact_hooks_harness_mocks_hook(fn) -> None:
    global _set_compact_hooks_harness_mocks_hook
    _set_compact_hooks_harness_mocks_hook = fn


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def reset_compact_session_state_mocks() -> None:
    """Reset per-test session-state mocks.

    Mirrors :func:`resetCompactSessionStateMocks`
    (``compact.hooks.harness.ts``).
    """
    if _set_compact_hooks_harness_mocks_hook is not None:
        _set_compact_hooks_harness_mocks_hook({"op": "resetSessionState"})
        return
    for key in list(_compact_hooks_harness_state.keys()):
        _compact_hooks_harness_state[key] = None
    _compact_hooks_harness_state["hookRunner"] = {}
    _compact_hooks_harness_state["sessionMessages"] = []


def reset_compact_hooks_harness_mocks() -> None:
    """Reset all compact-hooks-harness mocks to defaults.

    Mirrors :func:`resetCompactHooksHarnessMocks`
    (``compact.hooks.harness.ts``).
    """
    reset_compact_session_state_mocks()


async def load_compact_hooks_harness() -> Dict[str, Any]:
    """Load the compact-hooks harness and return its installed mocks.

    Mirrors :func:`loadCompactHooksHarness` (``compact.hooks.harness.ts``).
    """
    if _compact_hooks_harness_hook is not None:
        v = _compact_hooks_harness_hook({"op": "load"})
        if hasattr(v, "__await__"):
            return await v  # type: ignore[func-returns-value]
        return v or dict(_compact_hooks_harness_state)
    return dict(_compact_hooks_harness_state)


async def warm_compact_hooks_harness() -> Dict[str, Any]:
    """Warm the compact-hooks harness and return its installed mocks.

    Mirrors :func:`warmCompactHooksHarness` (``compact.hooks.harness.ts``).
    """
    if _compact_hooks_harness_hook is not None:
        v = _compact_hooks_harness_hook({"op": "warm"})
        if hasattr(v, "__await__"):
            return await v  # type: ignore[func-returns-value]
        return v or dict(_compact_hooks_harness_state)
    return dict(_compact_hooks_harness_state)


#: Test-only API surface mirroring the OpenClaw ``extraParamsTestApi`` global.
compact_hooks_test_api: Dict[str, Any] = {
    "resetCompactSessionStateMocks": reset_compact_session_state_mocks,
    "resetCompactHooksHarnessMocks": reset_compact_hooks_harness_mocks,
    "loadCompactHooksHarness": load_compact_hooks_harness,
    "warmCompactHooksHarness": warm_compact_hooks_harness,
}


__all__ = [
    "reset_compact_session_state_mocks",
    "reset_compact_hooks_harness_mocks",
    "load_compact_hooks_harness",
    "warm_compact_hooks_harness",
    "compact_hooks_test_api",
    "set_compact_hooks_harness_hook",
    "set_compact_hooks_harness_mocks_hook",
]
