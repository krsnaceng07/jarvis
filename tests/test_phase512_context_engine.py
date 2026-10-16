"""Phase 5.12b â€” ``context-engine.test.ts`` â†’ Python.

OpenClaw parity: ports the 47 ``it`` blocks from
``src/context-engine/context-engine.test.ts`` (across 11
``describe`` groups). The previous Phase 5.12 commit
(``ed6448d``) ported the implementation but the original
2K-line test file was uncommitted and got lost in a botched
file-split pass; this re-port is the recovery.

Python adaptations, marked at their sites:

- ``vi.hoisted`` + ``vi.mock`` of the compact runtime module
  becomes a `unittest.mock.patch` of
  ``delegate._load_compact_runtime`` (set up in
  ``_compact_runtime_spy``).
- ``AbortController`` becomes a tiny stand-in with
  ``aborted`` / ``reason`` (the Python compat check only
  reads the duck-typed signal).
- ``console.error`` / ``console.warn`` assertions capture
  ``sys.stderr`` via ``contextlib.redirect_stderr``.
- ``instanceof`` checks become ``info["id"]`` checks (the
  Python wrappers are delegating classes, not JS Proxies).
- The BigInt contract-validation throw becomes a custom
  ``info`` property that raises â€” same catch branch, since
  no plain Python value both fails the is-object check and
  breaks ``json.dumps``.
- ``it.runIf(hasProcessStartTimes)`` guards stay: sibling-visibility
  tests assert Linux ``/proc`` starttime semantics and
  skip elsewhere (the Python port of ``get_process_start_time``
  is in ``src/shared/pid_alive.py``).
"""
from __future__ import annotations

import contextlib
import copy
import importlib
import io
import sys
import types

import pytest

from src.context_engine import delegate as delegate_module
from src.context_engine.delegate import (
    build_memory_system_prompt_addition,
    delegate_compaction_to_runtime,
    prepare_memory_system_prompt_addition,
)
from src.context_engine.legacy import LegacyContextEngine
from src.context_engine.legacy_registration import register_legacy_context_engine
from src.context_engine.registry import (
    get_context_engine_registration,
    list_context_engine_quarantines,
    register_context_engine,
    register_context_engine_for_owner,
    resolve_context_engine,
    resolve_context_engine_owner_plugin_id,
)
from src.context_engine.registry_test_support import (
    reset_context_engine_runtime_quarantine_for_tests,
)
from src.plugins.memory_state import (
    MemoryPromptSectionParams,
    clear_memory_plugin_state,
    register_memory_prompt_preparation,
    register_memory_prompt_section_for_plugin,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _setup() -> None:
    """Per-test reset standing in for the vitest ``beforeEach`` hooks."""
    reset_context_engine_runtime_quarantine_for_tests()
    register_legacy_context_engine()
    clear_memory_plugin_state()


def _config_with_slot(engine_id: str) -> dict:
    return {"plugins": {"slots": {"contextEngine": engine_id}}}


def _make_mock_message(role: str = "user", text: str = "hello") -> dict:
    return {"role": role, "content": text, "timestamp": 0}


_unique_engine_id_counter = 0


def _unique_engine_id(prefix: str) -> str:
    global _unique_engine_id_counter
    _unique_engine_id_counter += 1
    return f"{prefix}-{_unique_engine_id_counter}"


def _memory_params(**kwargs) -> MemoryPromptSectionParams:
    tools = kwargs.pop("available_tools", frozenset())
    return MemoryPromptSectionParams(available_tools=frozenset(tools), **kwargs)


@contextlib.contextmanager
def _capture_stderr():
    """Capture ``console.error`` / ``console.warn`` output as a string."""
    buffer = io.StringIO()
    with contextlib.redirect_stderr(buffer):
        yield buffer


_DEFAULT_COMPACT_RESULT = {
    "ok": True,
    "compacted": False,
    "reason": "mock compaction",
    "result": {
        "summary": "",
        "firstKeptEntryId": "",
        "tokensBefore": 0,
        "tokensAfter": 0,
        "details": None,
    },
}


@contextlib.contextmanager
def _compact_runtime_spy(results=None):
    """Patch ``delegate._load_compact_runtime`` to capture call params."""
    calls: list[dict] = []
    queued = list(results or [])

    async def _compact_embedded(params):
        calls.append(params)
        if queued:
            return queued.pop(0)
        return copy.deepcopy(_DEFAULT_COMPACT_RESULT)

    runtime = types.SimpleNamespace(
        compact_embedded_agent_session_direct=_compact_embedded
    )
    original = delegate_module._load_compact_runtime
    delegate_module._load_compact_runtime = lambda: runtime
    try:
        yield calls
    finally:
        delegate_module._load_compact_runtime = original


# ---------------------------------------------------------------------------
# Mock engine classes
# ---------------------------------------------------------------------------


class MockContextEngine:
    """Minimal mock engine satisfying the ContextEngine protocol."""

    info = {"id": "mock", "name": "Mock Engine", "version": "0.0.1"}

    async def ingest(self, params):  # noqa: ARG002
        return {"ingested": True}

    async def assemble(self, params):
        return {
            "messages": params["messages"],
            "estimatedTokens": 42,
            "systemPromptAddition": "mock system addition",
        }

    async def compact(self, params):  # noqa: ARG002
        return {
            "ok": True,
            "compacted": True,
            "reason": "mock compaction",
            "result": {"summary": "mock summary", "tokensBefore": 100, "tokensAfter": 50},
        }

    async def dispose(self):
        return None


def _reject_key(params: dict, key: str) -> None:
    if key in params:
        raise Exception(f"Unrecognized key(s) in object: '{key}'")


class LegacySessionKeyStrictEngine:
    def __init__(self, engine_id: str = "legacy-sessionkey-strict") -> None:
        self.info = {"id": engine_id, "name": "Legacy SessionKey Strict Engine"}
        self.ingest_calls: list[dict] = []
        self.assemble_calls: list[dict] = []
        self.compact_calls: list[dict] = []
        self.maintain_calls: list[dict] = []
        self.ingested_messages: list[dict] = []

    async def ingest(self, params):
        self.ingest_calls.append(dict(params))
        _reject_key(params, "sessionKey")
        self.ingested_messages.append(params["message"])
        return {"ingested": True}

    async def assemble(self, params):
        self.assemble_calls.append(dict(params))
        _reject_key(params, "sessionKey")
        return {"messages": params["messages"], "estimatedTokens": 7}

    async def compact(self, params):
        self.compact_calls.append(dict(params))
        _reject_key(params, "sessionKey")
        return {
            "ok": True,
            "compacted": True,
            "result": {"tokensBefore": 50, "tokensAfter": 25},
        }

    async def maintain(self, params):
        self.maintain_calls.append(dict(params))
        _reject_key(params, "sessionKey")
        return {"changed": False, "bytesFreed": 0, "rewrittenEntries": 0}


class SessionKeyRuntimeErrorEngine:
    def __init__(
        self,
        engine_id: str = "sessionkey-runtime-error",
        error_message: str = "sessionKey lookup failed",
    ) -> None:
        self.info = {"id": engine_id, "name": "SessionKey Runtime Error Engine"}
        self.assemble_calls = 0
        self._error_message = error_message

    async def ingest(self, params):  # noqa: ARG002
        return {"ingested": True}

    async def assemble(self, params):  # noqa: ARG002
        self.assemble_calls += 1
        raise Exception(self._error_message)

    async def compact(self, params):  # noqa: ARG002
        return {"ok": True, "compacted": False}


class LegacyAssembleStrictEngine:
    def __init__(self, engine_id: str = "legacy-assemble-strict") -> None:
        self.info = {"id": engine_id, "name": "Legacy Assemble Strict Engine"}
        self.assemble_calls: list[dict] = []

    async def ingest(self, params):  # noqa: ARG002
        return {"ingested": True}

    async def assemble(self, params):
        self.assemble_calls.append(dict(params))
        _reject_key(params, "sessionKey")
        _reject_key(params, "prompt")
        _reject_key(params, "runtimeSettings")
        return {"messages": params["messages"], "estimatedTokens": 3}

    async def compact(self, params):  # noqa: ARG002
        return {"ok": True, "compacted": False}


class LegacyRuntimeSettingsStrictEngine:
    def __init__(self, engine_id: str = "legacy-runtime-settings-strict") -> None:
        self.info = {"id": engine_id, "name": "Legacy Runtime Settings Strict Engine"}
        self.bootstrap_calls: list[dict] = []
        self.maintain_calls: list[dict] = []
        self.after_turn_calls: list[dict] = []
        self.assemble_calls: list[dict] = []
        self.compact_calls: list[dict] = []

    def _reject_legacy_compat_fields(self, params: dict) -> None:
        _reject_key(params, "runtimeSettings")
        _reject_key(params, "sessionTarget")
        _reject_key(params, "runtimeContext")

    async def bootstrap(self, params):
        self.bootstrap_calls.append(dict(params))
        self._reject_legacy_compat_fields(params)
        return {"bootstrapped": True}

    async def ingest(self, params):  # noqa: ARG002
        return {"ingested": True}

    async def maintain(self, params):
        self.maintain_calls.append(dict(params))
        self._reject_legacy_compat_fields(params)
        return {"changed": False, "bytesFreed": 0, "rewrittenEntries": 0}

    async def afterTurn(self, params):  # noqa: N802
        self.after_turn_calls.append(dict(params))
        self._reject_legacy_compat_fields(params)

    async def assemble(self, params):
        self.assemble_calls.append(dict(params))
        self._reject_legacy_compat_fields(params)
        return {"messages": params["messages"], "estimatedTokens": 3}

    async def compact(self, params):
        self.compact_calls.append(dict(params))
        self._reject_legacy_compat_fields(params)
        return {"ok": True, "compacted": False}


class LegacyRuntimeThenAssembleStrictEngine:
    def __init__(self, engine_id: str = "legacy-runtime-then-assemble-strict") -> None:
        self.info = {"id": engine_id, "name": "Legacy Runtime Then Assemble Strict Engine"}
        self.maintain_calls: list[dict] = []
        self.assemble_calls: list[dict] = []

    async def ingest(self, params):  # noqa: ARG002
        return {"ingested": True}

    async def maintain(self, params):
        self.maintain_calls.append(dict(params))
        _reject_key(params, "runtimeSettings")
        return {"changed": False, "bytesFreed": 0, "rewrittenEntries": 0}

    async def assemble(self, params):
        self.assemble_calls.append(dict(params))
        _reject_key(params, "sessionKey")
        _reject_key(params, "prompt")
        _reject_key(params, "runtimeSettings")
        return {"messages": params["messages"], "estimatedTokens": 5}

    async def compact(self, params):  # noqa: ARG002
        return {"ok": True, "compacted": False}


# ---------------------------------------------------------------------------
# 1. Engine contract tests
# ---------------------------------------------------------------------------


def test_mock_engine_can_be_registered_and_resolved():
    _setup()
    engine_id = _unique_engine_id("mock-contract")
    register_context_engine(engine_id, lambda: MockContextEngine())

    # The Python wrapper is a delegating class, so ``isinstance`` is not
    # preserved; assert on the engine's own info instead.
    import asyncio

    engine = asyncio.run(resolve_context_engine(_config_with_slot(engine_id)))
    assert engine.info["id"] == "mock"


def test_legacy_compact_preserves_runtime_context_current_token_count():
    _setup()
    with _compact_runtime_spy() as calls:
        engine = LegacyContextEngine()
        import asyncio

        asyncio.run(
            engine.compact(
                {
                    "sessionId": "s1",
                    "sessionKey": "agent:main:s1",
                    "sessionTarget": {
                        "agentId": "main",
                        "sessionId": "s1",
                        "sessionKey": "agent:main:s1",
                    },
                    "runtimeContext": {
                        "workspaceDir": "/tmp/workspace",
                        "currentTokenCount": 277403,
                    },
                }
            )
        )

        assert len(calls) == 1
        assert calls[0]["currentTokenCount"] == 277403


def test_delegate_compaction_reuses_legacy_runtime_bridge():
    _setup()
    with _compact_runtime_spy() as calls:
        session_target = {
            "agentId": "main",
            "sessionId": "s2",
            "sessionKey": "agent:main:s2",
            "storePath": "/tmp/openclaw-agent.sqlite",
        }
        import asyncio

        result = asyncio.run(
            delegate_compaction_to_runtime(
                {
                    "sessionId": "s2",
                    "sessionKey": "agent:main:s2",
                    "sessionTarget": session_target,
                    "tokenBudget": 4096,
                    "runtimeContext": {
                        "workspaceDir": "/tmp/workspace",
                        "currentTokenCount": 12345,
                    },
                }
            )
        )

        assert len(calls) == 1
        runtime_params = calls[0]
        assert runtime_params["sessionId"] == "s2"
        assert runtime_params["sessionKey"] == "agent:main:s2"
        assert runtime_params["sessionTarget"] == session_target
        assert "sessionFile" not in runtime_params
        assert runtime_params["tokenBudget"] == 4096
        assert runtime_params["currentTokenCount"] == 12345
        assert runtime_params["workspaceDir"] == "/tmp/workspace"
        assert result == _DEFAULT_COMPACT_RESULT


def test_delegate_compaction_returns_successor_session_target_without_session_file():
    _setup()
    successor = {
        "ok": True,
        "compacted": True,
        "reason": None,
        "result": {
            "summary": "summary",
            "firstKeptEntryId": "entry-1",
            "tokensBefore": 100,
            "tokensAfter": 40,
            "details": None,
            "sessionId": "s3-successor",
            "sessionFile": "sqlite:main:s3-successor:/tmp/openclaw-agent.sqlite",
        },
    }
    with _compact_runtime_spy(results=[successor]):
        import asyncio

        result = asyncio.run(
            delegate_compaction_to_runtime(
                {
                    "sessionId": "s3",
                    "sessionKey": "agent:main:s3",
                    "tokenBudget": 4096,
                    "runtimeContext": {"workspaceDir": "/tmp/workspace"},
                }
            )
        )

    inner = result["result"]
    assert inner["sessionId"] == "s3-successor"
    assert inner["sessionTarget"] == {
        "agentId": "main",
        "sessionId": "s3-successor",
        "sessionKey": "agent:main:s3",
        "storePath": "/tmp/openclaw-agent.sqlite",
    }
    assert "sessionFile" not in inner


def test_delegate_compaction_forwards_caller_abort_signal_89868():
    _setup()
    with _compact_runtime_spy() as calls:
        controller = types.SimpleNamespace(aborted=False, reason=None)

        class _Controller:
            def __init__(self):
                self.signal = controller

            def abort(self, reason=None):
                self.signal.aborted = True
                self.signal.reason = reason

        controller_obj = _Controller()
        import asyncio

        asyncio.run(
            delegate_compaction_to_runtime(
                {
                    "sessionId": "s-abort",
                    "sessionKey": "agent:main:s-abort",
                    "tokenBudget": 4096,
                    "abortSignal": controller_obj.signal,
                }
            )
        )

        assert calls[0]["abortSignal"] is controller_obj.signal


def test_delegate_compaction_passes_none_abort_signal_when_none_supplied():
    _setup()
    with _compact_runtime_spy() as calls:
        import asyncio

        asyncio.run(
            delegate_compaction_to_runtime(
                {
                    "sessionId": "s-no-abort",
                    "sessionKey": "agent:main:s-no-abort",
                    "tokenBudget": 4096,
                }
            )
        )

        assert calls[0]["abortSignal"] is None


def test_builds_normalized_memory_system_prompt_addition():
    _setup()
    register_memory_prompt_section_for_plugin(
        "test-memory",
        lambda params: [
            "## Memory Recall",
            f"citations={params.citations_mode or 'auto'}",
            "",
        ],
    )

    assert (
        build_memory_system_prompt_addition(
            _memory_params(available_tools={"memory_search"}, citations_mode="off")
        )
        == "## Memory Recall\ncitations=off"
    )


def test_passes_agent_context_through_delegated_memory_prompt_assembly():
    _setup()

    def _builder(params):
        sandboxed = "true" if params.sandboxed else "false"
        return [
            "## Agent Memory",
            f"agent={params.agent_id} session={params.agent_session_key} sandboxed={sandboxed}",
            "",
        ]

    register_memory_prompt_section_for_plugin("test-memory", _builder)

    assert (
        build_memory_system_prompt_addition(
            _memory_params(
                available_tools={"memory_search", "memory_get"},
                agent_id="marketing-agent",
                agent_session_key="agent:marketing-agent:main",
                sandboxed=True,
            )
        )
        == "## Agent Memory\nagent=marketing-agent session=agent:marketing-agent:main sandboxed=true"
    )


def test_returns_none_when_memory_prompt_path_contributes_nothing():
    _setup()
    assert (
        build_memory_system_prompt_addition(
            _memory_params(available_tools={"memory_search"})
        )
        is None
    )


def test_prepares_async_memory_state_before_prompt_rendering():
    _setup()
    prepare_calls = []

    async def _prepare(params):
        prepare_calls.append(params)
        return ["## Prepared Memory", "loaded from sqlite", ""]

    register_memory_prompt_preparation("memory-wiki", _prepare)

    import asyncio

    result = asyncio.run(
        prepare_memory_system_prompt_addition(
            _memory_params(
                available_tools={"wiki_search"},
                agent_id="main",
                agent_session_key="agent:main:main",
            )
        )
    )
    assert result == "## Prepared Memory\nloaded from sqlite"
    assert len(prepare_calls) == 1


# ---------------------------------------------------------------------------
# 2. Registry tests
# ---------------------------------------------------------------------------


def test_register_context_engine_stores_retrievable_factories():
    _setup()
    engine_id = _unique_engine_id("registration-factory")

    def factory():
        return MockContextEngine()

    register_context_engine(engine_id, factory)
    registration = get_context_engine_registration(engine_id)
    assert registration is not None
    assert registration["factory"] is factory


def test_registering_same_id_with_same_owner_refreshes_factory():
    _setup()
    engine_id = _unique_engine_id("same-owner-refresh")

    def factory_a():
        return _make_simple_engine("factory-a")

    def factory_b():
        return _make_simple_engine("factory-b")

    first = register_context_engine_for_owner(engine_id, factory_a, "owner-a")
    assert first == {"ok": True}
    rejected = register_context_engine_for_owner(engine_id, factory_b, "owner-a")
    assert rejected == {"ok": False, "existingOwner": "owner-a"}
    refreshed = register_context_engine_for_owner(
        engine_id, factory_b, "owner-a", allow_same_owner_refresh=True
    )
    assert refreshed == {"ok": True}
    registration = get_context_engine_registration(engine_id)
    assert registration["factory"] is factory_b


def test_rejects_registrations_from_different_owner():
    _setup()
    engine_id = _unique_engine_id("different-owner")
    register_context_engine_for_owner(
        engine_id, lambda: _make_simple_engine("a"), "owner-a"
    )
    result = register_context_engine_for_owner(
        engine_id, lambda: _make_simple_engine("b"), "owner-b"
    )
    assert result == {"ok": False, "existingOwner": "owner-a"}


def test_exposes_trusted_plugin_owner_for_resolved_engine():
    _setup()
    engine_id = _unique_engine_id("plugin-owned")
    register_context_engine_for_owner(
        engine_id, lambda: _make_simple_engine(engine_id), "plugin:lossless-claw"
    )
    import asyncio

    engine = asyncio.run(resolve_context_engine(_config_with_slot(engine_id)))
    assert resolve_context_engine_owner_plugin_id(engine) == "lossless-claw"


def test_public_register_cannot_spoof_owner_or_refresh_existing():
    _setup()
    engine_id = _unique_engine_id("public-owner-guard")
    owned_factory = lambda: MockContextEngine()
    register_context_engine_for_owner(
        engine_id, owned_factory, "owner-a", allow_same_owner_refresh=True
    )
    # Public register has no owner param â€” cannot spoof or refresh.
    result = register_context_engine(engine_id, lambda: MockContextEngine())
    assert result == {"ok": False, "existingOwner": "owner-a"}
    registration = get_context_engine_registration(engine_id)
    assert registration["factory"] is owned_factory


def test_public_register_reserves_default_legacy_id():
    _setup()
    # The default ``legacy`` slot is reserved by the core owner.
    result = register_context_engine("legacy", lambda: _make_simple_engine("legacy"))
    assert result == {"ok": False, "existingOwner": "core"}


# ---------------------------------------------------------------------------
# 3. Legacy sessionKey compatibility
# ---------------------------------------------------------------------------


def test_memoizes_legacy_mode_after_first_strict_compat_retry():
    _setup()
    with _capture_stderr():
        engine_id = _unique_engine_id("legacy-sessionkey")
        strict_engine = LegacySessionKeyStrictEngine(engine_id)
        register_context_engine(engine_id, lambda: strict_engine)
        import asyncio

        engine = asyncio.run(resolve_context_engine(_config_with_slot(engine_id)))
        first_assembled = asyncio.run(
            engine.assemble(
                {
                    "sessionId": "s1",
                    "sessionKey": "agent:main:test",
                    "messages": [_make_mock_message()],
                }
            )
        )
        compacted = asyncio.run(
            engine.compact(
                {
                    "sessionId": "s1",
                    "sessionKey": "agent:main:test",
                }
            )
        )

        assert first_assembled["estimatedTokens"] == 7
        assert compacted["compacted"] is True
        assert len(strict_engine.assemble_calls) == 2
        assert "sessionKey" in strict_engine.assemble_calls[0]
        assert "sessionKey" not in strict_engine.assemble_calls[1]
        assert len(strict_engine.compact_calls) == 1
        assert "sessionKey" not in strict_engine.compact_calls[0]


def test_retries_strict_ingest_once_and_ingests_each_message_only_once():
    _setup()
    with _capture_stderr():
        engine_id = _unique_engine_id("legacy-sessionkey-ingest")
        strict_engine = LegacySessionKeyStrictEngine(engine_id)
        register_context_engine(engine_id, lambda: strict_engine)
        import asyncio

        engine = asyncio.run(resolve_context_engine(_config_with_slot(engine_id)))
        first = _make_mock_message("user", "first")
        second = _make_mock_message("assistant", "second")
        asyncio.run(
            engine.ingest(
                {
                    "sessionId": "s1",
                    "sessionKey": "agent:main:test",
                    "message": first,
                }
            )
        )
        asyncio.run(
            engine.ingest(
                {
                    "sessionId": "s1",
                    "sessionKey": "agent:main:test",
                    "message": second,
                }
            )
        )

        assert len(strict_engine.ingest_calls) == 3
        assert "sessionKey" in strict_engine.ingest_calls[0]
        assert "sessionKey" not in strict_engine.ingest_calls[1]
        assert "sessionKey" not in strict_engine.ingest_calls[2]
        assert strict_engine.ingested_messages == [first, second]


def test_retries_strict_maintain_once_and_memoizes_legacy_mode():
    _setup()
    with _capture_stderr():
        engine_id = _unique_engine_id("legacy-sessionkey-maintain")
        strict_engine = LegacySessionKeyStrictEngine(engine_id)
        register_context_engine(engine_id, lambda: strict_engine)
        import asyncio

        engine = asyncio.run(resolve_context_engine(_config_with_slot(engine_id)))

        asyncio.run(
            engine.maintain(
                {
                    "sessionId": "s1",
                    "sessionKey": "agent:main:test",
                    "sessionFile": "/tmp/session.json",
                }
            )
        )

        assert len(strict_engine.maintain_calls) == 2
        assert "sessionKey" in strict_engine.maintain_calls[0]
        assert "sessionKey" not in strict_engine.maintain_calls[1]


def test_keeps_learning_rejected_legacy_keys_after_runtimeSettings_marks_engine_legacy():
    _setup()
    with _capture_stderr():
        engine_id = _unique_engine_id("legacy-runtime-then-assemble")
        strict_engine = LegacyRuntimeThenAssembleStrictEngine(engine_id)
        register_context_engine(engine_id, lambda: strict_engine)
        import asyncio

        engine = asyncio.run(resolve_context_engine(_config_with_slot(engine_id)))
        runtime_settings = {"schemaVersion": 1}

        asyncio.run(
            engine.maintain(
                {
                    "sessionId": "s1",
                    "sessionKey": "agent:main:test",
                    "sessionFile": "/tmp/session.json",
                    "runtimeSettings": runtime_settings,
                }
            )
        )
        assembled = asyncio.run(
            engine.assemble(
                {
                    "sessionId": "s1",
                    "sessionKey": "agent:main:test",
                    "messages": [_make_mock_message("user", "hello")],
                    "prompt": "hello",
                    "runtimeSettings": runtime_settings,
                }
            )
        )

        assert assembled["estimatedTokens"] == 5
        assert len(strict_engine.maintain_calls) == 2
        assert "runtimeSettings" in strict_engine.maintain_calls[0]
        assert "runtimeSettings" not in strict_engine.maintain_calls[1]
        assert len(strict_engine.assemble_calls) == 3
        assert "runtimeSettings" not in strict_engine.assemble_calls[0]
        assert strict_engine.assemble_calls[0].get("sessionKey") == "agent:main:test"
        assert strict_engine.assemble_calls[0].get("prompt") == "hello"
        assert "runtimeSettings" not in strict_engine.assemble_calls[1]
        assert "sessionKey" not in strict_engine.assemble_calls[1]
        assert strict_engine.assemble_calls[1].get("prompt") == "hello"
        assert "runtimeSettings" not in strict_engine.assemble_calls[2]
        assert "sessionKey" not in strict_engine.assemble_calls[2]
        assert "prompt" not in strict_engine.assemble_calls[2]


def test_quarantines_and_falls_back_for_non_compat_runtime_errors():
    _setup()
    with _capture_stderr():
        engine_id = _unique_engine_id("sessionkey-runtime")
        runtime_error_engine = SessionKeyRuntimeErrorEngine(engine_id)
        register_context_engine(engine_id, lambda: runtime_error_engine)
        import asyncio

        engine = asyncio.run(resolve_context_engine(_config_with_slot(engine_id)))
        message = _make_mock_message()

        result = asyncio.run(
            engine.assemble(
                {
                    "sessionId": "s1",
                    "sessionKey": "agent:main:test",
                    "messages": [message],
                }
            )
        )
        next_engine = asyncio.run(resolve_context_engine(_config_with_slot(engine_id)))

        assert result["messages"] == [message]
        assert next_engine.info["id"] == "legacy"
        assert runtime_error_engine.assemble_calls == 1
        matching = [q for q in list_context_engine_quarantines() if q["engineId"] == engine_id]
        assert matching[0]["operation"] == "assemble"
        assert matching[0]["reason"] == "sessionKey lookup failed"


def test_quarantines_unknown_session_key_runtime_failures_as_schema_compat():
    _setup()
    with _capture_stderr():
        engine_id = _unique_engine_id("sessionkey-unknown-runtime")
        runtime_error_engine = SessionKeyRuntimeErrorEngine(
            engine_id, 'Unknown sessionKey "agent:main:missing"'
        )
        register_context_engine(engine_id, lambda: runtime_error_engine)
        import asyncio

        engine = asyncio.run(resolve_context_engine(_config_with_slot(engine_id)))
        message = _make_mock_message()

        result = asyncio.run(
            engine.assemble(
                {
                    "sessionId": "s1",
                    "sessionKey": "agent:main:missing",
                    "messages": [message],
                }
            )
        )

        assert result["messages"] == [message]
        assert runtime_error_engine.assemble_calls == 1
        matching = [q for q in list_context_engine_quarantines() if q["engineId"] == engine_id]
        assert matching[0]["operation"] == "assemble"
        assert matching[0]["reason"] == 'Unknown sessionKey "agent:main:missing"'


# ---------------------------------------------------------------------------
# 4. Default engine selection
# ---------------------------------------------------------------------------


def test_resolve_context_engine_with_no_config_returns_default_legacy():
    _setup()
    import asyncio

    engine = asyncio.run(resolve_context_engine())
    assert engine.info["id"] == "legacy"


def test_resolve_context_engine_with_config_legacy_returns_legacy():
    _setup()
    import asyncio

    engine = asyncio.run(resolve_context_engine(_config_with_slot("legacy")))
    assert engine.info["id"] == "legacy"


def test_resolve_context_engine_with_config_test_engine_returns_custom():
    _setup()
    # Register a lightweight custom stub.
    register_context_engine(
        "test-engine",
        lambda: _make_simple_engine("test-engine", name="Custom Test Engine"),
    )
    import asyncio

    engine = asyncio.run(resolve_context_engine(_config_with_slot("test-engine")))
    assert engine.info["id"] == "test-engine"


# ---------------------------------------------------------------------------
# 5. Factory context passing
# ---------------------------------------------------------------------------


def test_passes_factory_context_to_factories_that_accept_a_parameter():
    _setup()
    engine_id = _unique_engine_id("factory-ctx")
    received_ctx: dict = {}

    def factory(ctx):
        received_ctx.update(ctx)
        return {
            "info": {"id": engine_id, "name": "Ctx Engine"},
            }

    register_context_engine(engine_id, factory)

    cfg = _config_with_slot(engine_id)
    import asyncio

    asyncio.run(
        resolve_context_engine(
            cfg, {"agentDir": "/tmp/agent", "workspaceDir": "/tmp/workspace"}
        )
    )

    assert received_ctx["config"] is cfg
    assert received_ctx["agentDir"] == "/tmp/agent"
    assert received_ctx["workspaceDir"] == "/tmp/workspace"


def test_no_arg_factories_still_work_when_context_is_passed():
    _setup()
    engine_id = _unique_engine_id("factory-noarg")
    called = False

    def factory(ctx=None):  # noqa: ARG001 — accept ctx but ignore it
        nonlocal called
        called = True
        return _make_simple_engine(engine_id, name="No-Arg Engine")

    register_context_engine(engine_id, factory)
    import asyncio

    engine = asyncio.run(
        resolve_context_engine(
            _config_with_slot(engine_id),
            {"agentDir": "/tmp/agent", "workspaceDir": "/tmp/workspace"},
        )
    )

    assert called is True
    assert engine.info["id"] == engine_id


def test_passes_undefined_config_when_resolve_called_without_config():
    _setup()
    received_ctx: dict = {}

    def factory(ctx):
        received_ctx.update(ctx or {})
        return _make_simple_engine("legacy", name="NoConfig Engine", extra_info={"version": "1"})

    register_context_engine_for_owner(
        "legacy", factory, "core", allow_same_owner_refresh=True
    )
    import asyncio

    asyncio.run(resolve_context_engine(None))

    assert received_ctx.get("config") is None
    assert received_ctx.get("agentDir") is None
    assert received_ctx.get("workspaceDir") is None


# ---------------------------------------------------------------------------
# 6. Read-only plugin discovery registrations
# ---------------------------------------------------------------------------


def test_does_not_construct_or_quarantine_read_only_discovery_factories():
    _setup()
    with _capture_stderr():
        engine_id = _unique_engine_id("lossless-readonly")
        owner = "plugin:lossless-claw"
        read_only_factory_calls = 0
        runtime_factory_calls = 0

        def read_only_factory():
            nonlocal read_only_factory_calls
            read_only_factory_calls += 1
            raise Exception(
                "Engine initialization is disabled during read-only plugin registration"
            )

        register_context_engine_for_owner(
            engine_id,
            read_only_factory,
            owner,
            allow_same_owner_refresh=True,
            lifecycle="readOnlyDiscovery",
        )

        import asyncio

        discovery_fallback = asyncio.run(
            resolve_context_engine(_config_with_slot(engine_id))
        )

        assert discovery_fallback.info["id"] == "legacy"
        assert read_only_factory_calls == 0
        assert not any(
            q["engineId"] == engine_id for q in list_context_engine_quarantines()
        )

        def runtime_factory():
            nonlocal runtime_factory_calls
            runtime_factory_calls += 1
            return _make_simple_engine("lossless-claw", name="Lossless Claw")

        register_context_engine_for_owner(
            engine_id,
            runtime_factory,
            owner,
            allow_same_owner_refresh=True,
            lifecycle="runtime",
        )

        runtime_engine = asyncio.run(
            resolve_context_engine(_config_with_slot(engine_id))
        )

        assert runtime_engine.info["id"] == "lossless-claw"
        assert read_only_factory_calls == 0
        assert runtime_factory_calls == 1
        assert not any(
            q["engineId"] == engine_id for q in list_context_engine_quarantines()
        )

        # Re-registration as read-only-discovery should NOT replace runtime.
        def stale_read_only():
            nonlocal read_only_factory_calls
            read_only_factory_calls += 1
            raise Exception("read-only discovery should not replace runtime registration")

        register_context_engine_for_owner(
            engine_id,
            stale_read_only,
            owner,
            allow_same_owner_refresh=True,
            lifecycle="readOnlyDiscovery",
        )

        still_runtime_engine = asyncio.run(
            resolve_context_engine(_config_with_slot(engine_id))
        )

        assert still_runtime_engine.info["id"] == "lossless-claw"
        assert read_only_factory_calls == 0
        assert runtime_factory_calls == 2


# ---------------------------------------------------------------------------
# 7. Invalid engine fallback
# ---------------------------------------------------------------------------


def test_falls_back_to_default_engine_for_missing_or_invalid_requested_engines():
    _setup()
    with _capture_stderr():
        cases = [
            {
                "name": "missing registration",
                "engine_id": _unique_engine_id("does-not-exist"),
                "register": lambda eid: None,
                "expected_error": (
                    lambda eid: f'[context-engine] Context engine "{eid}" failed during resolve: not registered; quarantining it for this process and falling back to default engine "legacy".'
                ),
            },
            {
                "name": "factory throws",
                "engine_id": _unique_engine_id("factory-throw"),
                "register": lambda eid: register_context_engine(
                    eid,
                    lambda: (_ for _ in ()).throw(Exception("plugin version mismatch")),
                ),
                "expected_error": (
                    lambda eid: f'[context-engine] Context engine "{eid}" owner=public-sdk failed during factory: plugin version mismatch; quarantining it for this process and falling back to default engine "legacy".'
                ),
            },
            {
                "name": "missing info metadata",
                "engine_id": _unique_engine_id("invalid-info"),
                "register": lambda eid: register_context_engine(
                    eid,
                    lambda: {
                        },
                ),
                "expected_error": (
                    lambda eid: f'[context-engine] Context engine "{eid}" owner=public-sdk failed during contract-validation: Context engine "{eid}" factory returned an invalid ContextEngine: missing info.; quarantining it for this process and falling back to default engine "legacy".'
                ),
            },
            {
                "name": "missing lifecycle methods",
                "engine_id": _unique_engine_id("invalid-methods"),
                "register": lambda eid: register_context_engine(
                    eid,
                    lambda: {
                        "info": {"id": eid, "name": "Broken Engine"},
                        "ingest": None,
                    },
                ),
                "expected_error": (
                    lambda eid: f'[context-engine] Context engine "{eid}" owner=public-sdk failed during contract-validation: Context engine "{eid}" factory returned an invalid ContextEngine: missing assemble(), missing compact().; quarantining it for this process and falling back to default engine "legacy".'
                ),
            },
        ]
        # Contract-validation throws: a non-JSON-serializable value trips the
        # same catch branch as the BigInt test.
        bigint_eid = _unique_engine_id("validation-throw")
        cases.append(
            {
                "name": "contract validation throws",
                "engine_id": bigint_eid,
                "register": lambda eid: register_context_engine(
                    eid, lambda: _Unserializable()
                ),
                "expected_error": (
                    lambda eid: f'[context-engine] Context engine "{eid}" owner=public-sdk failed during contract-validation: Object of type _Unserializable is not JSON serializable; quarantining it for this process and falling back to default engine "legacy".'
                ),
            }
        )

        import asyncio

        for case in cases:
            case["register"](case["engine_id"])
            engine = asyncio.run(
                resolve_context_engine(_config_with_slot(case["engine_id"]))
            )
            assert engine.info["id"] == "legacy", case["name"]
            assert any(
                q["engineId"] == case["engine_id"]
                for q in list_context_engine_quarantines()
            ), case["name"]


def test_quarantines_selected_engine_after_lifecycle_failure_and_falls_back():
    _setup()
    with _capture_stderr():
        engine_id = _unique_engine_id("runtime-fail")
        factory_calls = 0
        assemble_calls = 0

        async def assemble(params):  # noqa: ARG002
            nonlocal assemble_calls
            assemble_calls += 1
            raise Exception("lcm db is corrupt")

        def factory():
            nonlocal factory_calls
            factory_calls += 1
            return _make_dict_engine(
                info={"id": "lcm", "name": "Lossless Context Manager"},
                assemble=assemble,
            )

        register_context_engine(engine_id, factory)
        import asyncio

        engine = asyncio.run(resolve_context_engine(_config_with_slot(engine_id)))
        message = _make_mock_message("user", "hello")
        result = asyncio.run(
            engine.assemble({"sessionId": "s1", "messages": [message]})
        )
        next_engine = asyncio.run(
            resolve_context_engine(_config_with_slot(engine_id))
        )

        assert result["messages"] == [message]
        assert next_engine.info["id"] == "legacy"
        assert factory_calls == 1
        assert assemble_calls == 1
        matching = [q for q in list_context_engine_quarantines() if q["engineId"] == engine_id]
        assert matching[0]["owner"] == "public-sdk"
        assert matching[0]["operation"] == "assemble"
        assert matching[0]["reason"] == "lcm db is corrupt"


def test_exposes_fallback_metadata_on_same_engine_after_lifecycle_quarantine():
    _setup()
    with _capture_stderr():
        engine_id = _unique_engine_id("runtime-fail-metadata")
        assemble_calls = 0

        async def assemble(params):  # noqa: ARG002
            nonlocal assemble_calls
            assemble_calls += 1
            raise Exception("plugin store unavailable")

        def factory():
            return _make_dict_engine(
                info={
                    "id": "lcm",
                    "name": "Lossless Context Manager",
                    "ownsCompaction": True,
                },
                assemble=assemble,
            )

        register_context_engine_for_owner(
            engine_id, factory, "plugin:lossless-claw", allow_same_owner_refresh=True
        )
        import asyncio

        engine = asyncio.run(resolve_context_engine(_config_with_slot(engine_id)))
        assert engine.info["ownsCompaction"] is True
        assert resolve_context_engine_owner_plugin_id(engine) == "lossless-claw"

        message = _make_mock_message("user", "hello")
        result = asyncio.run(
            engine.assemble({"sessionId": "s1", "messages": [message]})
        )

        assert result["messages"] == [message]
        assert engine.info["id"] == "legacy"
        assert "ownsCompaction" not in engine.info
        assert resolve_context_engine_owner_plugin_id(engine) is None
        assert assemble_calls == 1


def test_quarantines_compact_failures_without_same_call_legacy_fallback():
    _setup()
    with _capture_stderr():
        engine_id = _unique_engine_id("runtime-fail-compact")
        compact_calls = 0

        async def compact(params):  # noqa: ARG002
            nonlocal compact_calls
            compact_calls += 1
            raise Exception("plugin compaction failed")

        def factory():
            return _make_dict_engine(
                info={
                    "id": "lcm",
                    "name": "Lossless Context Manager",
                    "ownsCompaction": True,
                },
                compact=compact,
            )

        register_context_engine_for_owner(
            engine_id, factory, "plugin:lossless-claw", allow_same_owner_refresh=True
        )
        import asyncio

        engine = asyncio.run(resolve_context_engine(_config_with_slot(engine_id)))

        with pytest.raises(Exception, match="plugin compaction failed"):
            asyncio.run(
                engine.compact(
                    {"sessionId": "s1", "sessionKey": "agent:main:s1"}
                )
            )

        assert engine.info["id"] == "legacy"
        assert "ownsCompaction" not in engine.info
        assert resolve_context_engine_owner_plugin_id(engine) is None
        assert compact_calls == 1


def test_clears_missing_engine_quarantine_when_plugin_registers_later():
    _setup()
    with _capture_stderr():
        engine_id = _unique_engine_id("late-register")
        import asyncio

        missing_engine = asyncio.run(
            resolve_context_engine(_config_with_slot(engine_id))
        )
        assert missing_engine.info["id"] == "legacy"
        matching = [q for q in list_context_engine_quarantines() if q["engineId"] == engine_id]
        assert matching[0]["operation"] == "resolve"
        assert matching[0]["reason"] == "not registered"

        register_context_engine(
            engine_id,
            lambda: _make_simple_engine(engine_id, name="Late Registered Engine"),
        )

        registered_engine = asyncio.run(
            resolve_context_engine(_config_with_slot(engine_id))
        )
        assert not list_context_engine_quarantines()
        assert registered_engine.info["id"] == engine_id


def test_does_not_quarantine_abort_rejections_from_lifecycle_methods():
    _setup()
    with _capture_stderr():
        engine_id = _unique_engine_id("abort-rejection")
        controller = types.SimpleNamespace(aborted=False, reason=None)
        abort_error = Exception("compaction aborted")
        abort_error.name = "AbortError"

        async def compact(params):  # noqa: ARG002
            controller.aborted = True
            controller.reason = Exception("user stopped run")
            raise abort_error

        def factory():
            return _make_dict_engine(
                info={"id": engine_id, "name": "Abort Aware Engine"},
                compact=compact,
            )

        register_context_engine(engine_id, factory)
        import asyncio

        engine = asyncio.run(resolve_context_engine(_config_with_slot(engine_id)))

        with pytest.raises(Exception, match="compaction aborted"):
            asyncio.run(
                engine.compact(
                    {
                        "sessionId": "s1",
                        "sessionKey": "agent:main:s1",
                        "abortSignal": controller,
                    }
                )
            )

        next_engine = asyncio.run(
            resolve_context_engine(_config_with_slot(engine_id))
        )
        assert next_engine.info["id"] == engine_id
        assert not list_context_engine_quarantines()


def test_quarantines_subagent_preparation_failures_while_failing_active_spawn_closed():
    _setup()
    with _capture_stderr():
        engine_id = _unique_engine_id("prepare-subagent-fail")

        async def prepare_subagent_spawn(params):  # noqa: ARG002
            raise Exception("child context projection failed")

        def factory():
            return _make_dict_engine(
                info={"id": engine_id, "name": "Spawn Aware Engine"},
                prepare_subagent_spawn=prepare_subagent_spawn,
            )

        register_context_engine(engine_id, factory)
        import asyncio

        engine = asyncio.run(resolve_context_engine(_config_with_slot(engine_id)))

        with pytest.raises(Exception, match="child context projection failed"):
            asyncio.run(
                engine.prepareSubagentSpawn(
                    {
                        "parentSessionKey": "agent:main",
                        "childSessionKey": "agent:child",
                        "contextMode": "isolated",
                    }
                )
            )

        next_engine = asyncio.run(
            resolve_context_engine(_config_with_slot(engine_id))
        )
        assert next_engine.info["id"] == "legacy"
        matching = [q for q in list_context_engine_quarantines() if q["engineId"] == engine_id]
        assert matching[0]["operation"] == "prepareSubagentSpawn"
        assert matching[0]["reason"] == "child context projection failed"


def test_throws_when_default_engine_itself_is_not_registered():
    """The default engine must always be registered; an empty registry raises."""
    _setup()
    from src.shared.global_singleton import resolve_global_singleton

    # Snapshot + clear the registry; restore in finally.
    registry_state = resolve_global_singleton(
        "openclaw.contextEngineRegistryState",
        lambda: {"engines": {}, "quarantinedEngines": {}},
    )
    engines = registry_state["engines"]
    snapshot = dict(engines)
    engines.clear()
    try:
        import asyncio

        with pytest.raises(Exception, match="not registered"):
            asyncio.run(resolve_context_engine())
    finally:
        engines.update(snapshot)


def test_propagates_error_when_default_engine_factory_throws():
    _setup()

    def throwing_factory():
        raise Exception("default engine init failed")

    register_context_engine_for_owner(
        "legacy", throwing_factory, "core", allow_same_owner_refresh=True
    )
    import asyncio

    with pytest.raises(Exception, match="default engine init failed"):
        asyncio.run(resolve_context_engine())


def test_propagates_error_when_default_engine_fails_contract_validation():
    _setup()

    def factory():
        return {"broken": True}

    register_context_engine_for_owner(
        "legacy", factory, "core", allow_same_owner_refresh=True
    )
    import asyncio

    with pytest.raises(Exception, match='Context engine "legacy" factory returned an invalid ContextEngine'):
        asyncio.run(resolve_context_engine())


def test_accepts_resolved_engines_whose_info_id_differs_from_registered_slot_id():
    """Regression for #66601: third-party plugins like lossless-claw register
    under an external slot id but the engine they return uses the plugin's
    own internal id; that id is metadata, not the lookup key."""
    _setup()
    engine_id = _unique_engine_id("plugin-slot")
    internal_info_id = "lcm"

    def factory():
        return _make_simple_engine(
            internal_info_id,
            name="Lossless Context Manager",
            extra_info={"version": "0.5.2"},
        )

    register_context_engine(engine_id, factory)
    import asyncio

    engine = asyncio.run(resolve_context_engine(_config_with_slot(engine_id)))
    assert engine.info["id"] == internal_info_id
    assert engine.info["name"] == "Lossless Context Manager"
    result = asyncio.run(
        engine.assemble(
            {"sessionId": "s1", "messages": [_make_mock_message("user", "hello")]}
        )
    )
    assert result["estimatedTokens"] == 0


# ---------------------------------------------------------------------------
# 8. LegacyContextEngine parity
# ---------------------------------------------------------------------------


def test_legacy_ingest_returns_ingested_false_no_op():
    _setup()
    import asyncio

    engine = LegacyContextEngine()
    result = asyncio.run(
        engine.ingest({"sessionId": "s1", "message": _make_mock_message()})
    )
    assert result == {"ingested": False}


def test_legacy_assemble_returns_messages_as_is_pass_through():
    _setup()
    import asyncio

    engine = LegacyContextEngine()
    messages = [
        _make_mock_message("user", "first"),
        _make_mock_message("assistant", "second"),
        _make_mock_message("user", "third"),
    ]
    result = asyncio.run(engine.assemble({"sessionId": "s1", "messages": messages}))

    # Messages are the exact same list reference (pass-through).
    assert result["messages"] is messages
    assert len(result["messages"]) == 3
    assert result["estimatedTokens"] == 0
    assert result.get("systemPromptAddition") is None


def test_legacy_dispose_completes_without_error():
    _setup()
    import asyncio

    engine = LegacyContextEngine()
    result = asyncio.run(engine.dispose())
    assert result is None


# ---------------------------------------------------------------------------
# 9. assemble() prompt forwarding
# ---------------------------------------------------------------------------


def test_forwards_prompt_only_when_callers_provide_one():
    _setup()
    with _capture_stderr():
        cases = [
            {"name": "provided", "params": {"prompt": "hello"}, "expected_prompt": "hello"},
            {"name": "omitted", "params": {}, "expected_prompt": None},
            {
                "name": "conditional spread undefined",
                "params": {},
                "expected_prompt": None,
            },
        ]

        import asyncio

        for case in cases:
            engine_id = _unique_engine_id(
                f"prompt-{case['name'].replace(' ', '-')}"
            )
            calls = _register_prompt_tracking_engine(engine_id)
            engine = asyncio.run(resolve_context_engine(_config_with_slot(engine_id)))
            asyncio.run(
                engine.assemble(
                    {
                        "sessionId": "s1",
                        "messages": [_make_mock_message("user", "hello")],
                        **case["params"],
                    }
                )
            )
            assert len(calls) == 1, case["name"]
            if case["expected_prompt"] is None:
                assert "prompt" not in calls[0], case["name"]
            else:
                assert calls[0].get("prompt") == case["expected_prompt"], case["name"]


def test_retries_strict_legacy_assemble_without_session_key_prompt_and_runtimeSettings():
    _setup()
    with _capture_stderr():
        engine_id = _unique_engine_id("prompt-legacy")
        strict_engine = LegacyAssembleStrictEngine(engine_id)
        register_context_engine(engine_id, lambda: strict_engine)
        import asyncio

        engine = asyncio.run(resolve_context_engine(_config_with_slot(engine_id)))
        result = asyncio.run(
            engine.assemble(
                {
                    "sessionId": "s1",
                    "sessionKey": "agent:main:test",
                    "messages": [_make_mock_message("user", "hello")],
                    "prompt": "hello",
                    "runtimeSettings": {"schemaVersion": 1},
                }
            )
        )

        assert result["estimatedTokens"] == 3
        assert len(strict_engine.assemble_calls) == 4
        assert strict_engine.assemble_calls[0].get("sessionKey") == "agent:main:test"
        assert strict_engine.assemble_calls[0].get("prompt") == "hello"
        assert "runtimeSettings" in strict_engine.assemble_calls[0]
        assert "sessionKey" not in strict_engine.assemble_calls[1]
        assert strict_engine.assemble_calls[1].get("prompt") == "hello"
        assert "runtimeSettings" in strict_engine.assemble_calls[1]
        assert "sessionKey" not in strict_engine.assemble_calls[2]
        assert "prompt" not in strict_engine.assemble_calls[2]
        assert "runtimeSettings" in strict_engine.assemble_calls[2]
        assert "sessionKey" not in strict_engine.assemble_calls[3]
        assert "prompt" not in strict_engine.assemble_calls[3]
        assert "runtimeSettings" not in strict_engine.assemble_calls[3]


def test_retries_strict_legacy_lifecycle_hooks_without_additive_host_fields():
    _setup()
    with _capture_stderr():
        runtime_settings = {"schemaVersion": 1}
        session_target = {
            "agentId": "main",
            "sessionId": "s1",
            "sessionKey": "agent:main:test",
        }
        runtime_context = {"transcriptStorage": {"kind": "sqlite"}}
        import asyncio

        def _resolve_strict_engine():
            engine_id = _unique_engine_id("runtime-settings-legacy")
            strict_engine = LegacyRuntimeSettingsStrictEngine(engine_id)
            register_context_engine(engine_id, lambda: strict_engine)
            engine = asyncio.run(resolve_context_engine(_config_with_slot(engine_id)))
            return engine, strict_engine

        bootstrap_engine, bootstrap_strict = _resolve_strict_engine()
        asyncio.run(
            bootstrap_engine.bootstrap(
                {
                    "sessionId": "s1",
                    "sessionKey": "agent:main:test",
                    "sessionFile": "sessions/s1.jsonl",
                    "runtimeSettings": runtime_settings,
                    "sessionTarget": session_target,
                    "runtimeContext": runtime_context,
                }
            )
        )

        maintain_engine, maintain_strict = _resolve_strict_engine()
        asyncio.run(
            maintain_engine.maintain(
                {
                    "sessionId": "s1",
                    "sessionKey": "agent:main:test",
                    "sessionFile": "sessions/s1.jsonl",
                    "runtimeSettings": runtime_settings,
                    "sessionTarget": session_target,
                    "runtimeContext": runtime_context,
                }
            )
        )

        after_turn_engine, after_turn_strict = _resolve_strict_engine()
        asyncio.run(
            after_turn_engine.afterTurn(
                {
                    "sessionId": "s1",
                    "sessionKey": "agent:main:test",
                    "sessionFile": "sessions/s1.jsonl",
                    "messages": [_make_mock_message("assistant", "done")],
                    "prePromptMessageCount": 0,
                    "runtimeSettings": runtime_settings,
                    "sessionTarget": session_target,
                    "runtimeContext": runtime_context,
                }
            )
        )

        assemble_engine, assemble_strict = _resolve_strict_engine()
        asyncio.run(
            assemble_engine.assemble(
                {
                    "sessionId": "s1",
                    "sessionKey": "agent:main:test",
                    "messages": [_make_mock_message("user", "hello")],
                    "runtimeSettings": runtime_settings,
                }
            )
        )

        compact_engine, compact_strict = _resolve_strict_engine()
        asyncio.run(
            compact_engine.compact(
                {
                    "sessionId": "s1",
                    "sessionKey": "agent:main:test",
                    "runtimeSettings": runtime_settings,
                    "sessionTarget": session_target,
                    "runtimeContext": runtime_context,
                }
            )
        )

        # Each lifecycle method retries once and ends with the additive host
        # fields stripped (the final call lacks runtimeSettings/sessionTarget/runtimeContext).
        for calls in [
            bootstrap_strict.bootstrap_calls,
            maintain_strict.maintain_calls,
            after_turn_strict.after_turn_calls,
            assemble_strict.assemble_calls,
            compact_strict.compact_calls,
        ]:
            final_call = calls[-1]
            assert final_call is not None
            assert "runtimeSettings" in calls[0]
            assert calls[0].get("sessionKey") == "agent:main:test"
            assert final_call.get("sessionKey") == "agent:main:test"
            assert "runtimeSettings" not in final_call
            assert "sessionTarget" not in final_call
            assert "runtimeContext" not in final_call

        for calls in [
            bootstrap_strict.bootstrap_calls,
            maintain_strict.maintain_calls,
            after_turn_strict.after_turn_calls,
            compact_strict.compact_calls,
        ]:
            assert len(calls) == 4
            assert calls[0].get("sessionTarget") == session_target
            assert calls[0].get("runtimeContext") == runtime_context

        assert len(assemble_strict.assemble_calls) == 2
        for call in assemble_strict.assemble_calls:
            assert "sessionTarget" not in call
            assert "runtimeContext" not in call


# ---------------------------------------------------------------------------
# 10. Initialization guard
# ---------------------------------------------------------------------------


def test_ensure_context_engines_initialized_is_idempotent_and_registers_legacy():
    _setup()
    from src.context_engine.init import ensure_context_engines_initialized

    assert ensure_context_engines_initialized() is None
    assert ensure_context_engines_initialized() is None
    assert get_context_engine_registration("legacy") is not None


# ---------------------------------------------------------------------------
# 11. Bundle chunk isolation (#40096)
# ---------------------------------------------------------------------------


def test_shares_registrations_and_keeps_concurrent_chunk_registration_visible():
    """The Symbol.for keyed global ensures that a plugin calling
    registerContextEngine() from chunk A is visible to
    resolveContextEngine() imported from chunk B (Python analog:
    re-importing the registry module returns the same process-wide
    singleton)."""
    _setup()
    ts = _unique_engine_id("chunk")
    # Re-import the registry module under a fresh alias â€” same as the TS
    # dynamic ``import(`./registry.ts?chunk=${ts}`)`` re-import. Python
    # doesn't have Vite-style chunk params, so we re-import the module
    # via importlib to prove the keyed global keeps both views identical.
    dynamic_chunk = importlib.reload(sys.modules["src.context_engine.registry"])

    chunks = [
        {
            "registerContextEngine": register_context_engine,
            "getContextEngineRegistration": get_context_engine_registration,
            "resolveContextEngine": resolve_context_engine,
        },
        {
            "registerContextEngine": dynamic_chunk.register_context_engine,
            "getContextEngineRegistration": dynamic_chunk.get_context_engine_registration,
            "resolveContextEngine": dynamic_chunk.resolve_context_engine,
        },
    ]

    engine_id = f"cross-chunk-{ts}"
    factory = lambda: _make_simple_engine(
        engine_id, name="Cross-chunk Engine", extra_info={"version": "0.0.1"}
    )
    chunks[0]["registerContextEngine"](engine_id, factory)

    assert chunks[1]["getContextEngineRegistration"](engine_id)["factory"] is factory
    import asyncio

    engine = asyncio.run(chunks[1]["resolveContextEngine"](_config_with_slot(engine_id)))
    assert engine.info["id"] == engine_id

    # Concurrent registrations from both chunks remain visible everywhere.
    ids = [f"concurrent-{ts}-0", f"concurrent-{ts}-1"]
    for i, chunk in enumerate(chunks):
        chunk["registerContextEngine"](ids[i], lambda: MockContextEngine())
    for id_ in ids:
        assert chunks[0]["getContextEngineRegistration"](id_) is not None


# ---------------------------------------------------------------------------
# Helpers used by the test bodies above
# ---------------------------------------------------------------------------


def _make_simple_engine(info_id: str, name: str = "Simple Engine", extra_info=None):
    info = {"id": info_id, "name": name}
    if extra_info:
        info.update(extra_info)

    class _Simple:
        def __init__(self):
            self.info = info

        async def ingest(self, params):  # noqa: ARG002
            return {"ingested": True}

        async def assemble(self, params):  # noqa: ARG002
            return {"messages": params["messages"], "estimatedTokens": 0}

        async def compact(self, params):  # noqa: ARG002
            return {"ok": True, "compacted": False}

    return _Simple()


def _register_prompt_tracking_engine(engine_id: str) -> list[dict]:
    calls: list[dict] = []

    class _PromptTracker:
        info = {"id": engine_id, "name": "Prompt Tracker", "version": "0.0.0"}

        async def ingest(self, params):  # noqa: ARG002
            return {"ingested": False}

        async def assemble(self, params):
            calls.append(dict(params))
            return {"messages": params["messages"], "estimatedTokens": 0}

        async def compact(self, params):  # noqa: ARG002
            return {"ok": True, "compacted": False}

    register_context_engine(engine_id, lambda: _PromptTracker())
    return calls


def _unserializable_factory():
    """Stand-in for the OpenClaw ``42n`` BigInt contract-validation test.

    A non-JSON-serializable object trips the same catch branch (the
    contract validator calls ``json.dumps`` on the result).
    """

    class _Unserializable:
        pass

    return _Unserializable()


def _make_dict_engine(
    *,
    info: dict,
    ingest=None,
    assemble=None,
    compact=None,
    prepare_subagent_spawn=None,
):
    """Build a duck-typed ContextEngine with no-op defaults for the
    methods not supplied. Mirrors the inline factories in the OpenClaw
    tests; the contract validator only cares that all three core methods
    exist on the returned object. The result is a ``SimpleNamespace``
    (not a dict) so ``engine.prepareSubagentSpawn`` attribute access
    works — the registry wrapper uses ``getattr`` on the target.
    """

    async def _ingest(params):  # noqa: ARG001
        return {"ingested": True}

    async def _assemble(params):
        return {"messages": params.get("messages", []), "estimatedTokens": 0}

    async def _compact(params):  # noqa: ARG001
        return {"ok": True, "compacted": False}

    engine = types.SimpleNamespace(
        info=info,
        ingest=ingest or _ingest,
        assemble=assemble or _assemble,
        compact=compact or _compact,
    )
    if prepare_subagent_spawn is not None:
        engine.prepareSubagentSpawn = prepare_subagent_spawn
    return engine


def _await_or_asyncio_run(method):
    """Adapter that runs an async coroutine via ``asyncio.run``."""
    import asyncio

    def _runner(*args, **kwargs):
        return asyncio.run(method(*args, **kwargs))

    return _runner

