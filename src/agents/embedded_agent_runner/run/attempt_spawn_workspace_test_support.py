"""Minimal parity for OpenClaw's attempt.spawn-workspace.test-support.

This module exposes `get_hoisted()` returning a hoisted-mocks dict used
by tests. The full OpenClaw harness is large; this minimal shim provides
no-op mocks and lightweight defaults so Python tests can import the
test-support surface and override individual mocks as needed.
"""
from __future__ import annotations

from typing import Any, Callable, Dict


def _noop(*_args, **_kwargs):
    return None


def _async_noop(*_args, **_kwargs):
    async def _coro():
        return None

    return _coro()


def get_hoisted() -> Dict[str, Any]:
    """Return a hoisted-mocks dict similar to OpenClaw's `getHoisted()`.

    Tests can import this module and patch entries on the returned dict.
    """
    return {
        "spawnSubagentDirectMock": _noop,
        "createAgentSessionMock": _noop,
        "applyExtraParamsToAgentMock": _noop,
        "sessionManagerOpenMock": _noop,
        "defaultResourceLoaderInitMock": _noop,
        "resolveSandboxContextMock": _noop,
        "ensureGlobalUndiciEnvProxyDispatcherMock": _noop,
        "ensureGlobalUndiciDispatcherStreamTimeoutsMock": _noop,
        "ensureGlobalUndiciStreamTimeoutsMock": _noop,
        "buildEmbeddedMessageActionDiscoveryInputMock": lambda params: params,
        "createOpenClawCodingToolsMock": lambda: [],
        "subscribeEmbeddedAgentSessionMock": lambda: None,
        "acquireSessionWriteLockMock": lambda *_args, **_kwargs: {"release": _noop},
        "installToolResultContextGuardMock": lambda *_args, **_kwargs: _noop,
        "installContextEngineLoopHookMock": lambda *_args, **_kwargs: _noop,
        "flushPendingToolResultsAfterIdleMock": _async_noop,
        "resolveBootstrapFilesForRunMock": lambda *_args, **_kwargs: [],
        "resolveBootstrapContextForRunMock": lambda *_args, **_kwargs: {"bootstrapFiles": [], "contextFiles": []},
        "isWorkspaceBootstrapPendingMock": lambda *_args, **_kwargs: False,
        "resolveContextInjectionModeMock": lambda: "always",
        "hasCompletedBootstrapTurnMock": lambda: False,
        "resolveEmbeddedRunSkillEntriesMock": lambda *_args, **_kwargs: {"shouldLoadSkillEntries": False, "skillEntries": None},
        "resolveSkillsPromptForRunMock": lambda *_args, **_kwargs: "",
        "supportsModelToolsMock": lambda *_args, **_kwargs: True,
        "getGlobalHookRunnerMock": lambda *_args, **_kwargs: None,
        "initializeGlobalHookRunnerMock": _noop,
        "runContextEngineMaintenanceMock": _async_noop,
        "prepareSessionManagerForRunMock": _async_noop,
        "detectAndLoadPromptImagesMock": lambda *_args, **_kwargs: {"images": [], "detectedRefs": [], "loadedCount": 0, "skippedCount": 0},
        "getHistoryLimitFromSessionKeyMock": lambda *_args, **_kwargs: None,
        "limitHistoryTurnsMock": lambda messages, limit=None: messages,
        "preemptiveCompactionCalls": [],
        "compactionReserveTokens": 0,
        "systemPromptTexts": [],
        "embeddedSystemPromptInputs": [],
        "trajectoryEvents": [],
        "sessionManager": {},
    }


__all__ = ["get_hoisted"]
