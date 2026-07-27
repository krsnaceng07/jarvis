"""Phase 5.12b — ``host-compat.test.ts`` → Python.

OpenClaw parity: ports the 5 ``it`` blocks from
``src/context-engine/host-compat.test.ts``.

Python adaptations:
- ``createEngine`` factory returns a plain dict satisfying the
  duck-typed ContextEngine protocol (info, ingest, assemble,
  compact). The Python ``host_compat`` module reads
  ``context_engine.info`` so a duck-typed dict with the same
  shape is sufficient.
- The generic CLI host is built via
  ``build_generic_cli_context_engine_host_support(backend_id="claude-cli")``
  (matches OpenClaw's helper).
- ``expect(() => ...).toThrow("...")`` becomes
  ``pytest.raises(RuntimeError, match=...)`` — the Python
  error message includes the engine id, operation, host label,
  missing/required/actual capabilities, and any
  ``unsupportedMessage`` from the engine.
"""
from __future__ import annotations

import pytest

from src.context_engine.host_compat import (
    CODEX_APP_SERVER_CONTEXT_ENGINE_HOST,
    OPENCLAW_EMBEDDED_CONTEXT_ENGINE_HOST,
    assert_context_engine_host_support,
    build_generic_cli_context_engine_host_support,
    evaluate_context_engine_host_support,
)


class _Engine:
    """Duck-typed ContextEngine stand-in.

    Mirrors the TypeScript ``createEngine`` helper. The Python
    ``host_compat`` module reads ``context_engine.info``, so a class
    with the same shape is sufficient.
    """

    def __init__(self, required_capabilities):
        self.info = {
            "id": "lossless-claw",
            "name": "Lossless",
            "hostRequirements": {
                "agent-run": {
                    "requiredCapabilities": list(required_capabilities),
                    "unsupportedMessage": (
                        "Use the native Codex or OpenClaw embedded runtime, "
                        "or switch contextEngine to legacy."
                    ),
                },
            },
        }

    async def ingest(self, params):  # noqa: ARG002 — protocol stub
        return {"ingested": True}

    async def assemble(self, params):  # noqa: ARG002 — protocol stub
        return {"messages": params.get("messages", []), "estimatedTokens": 0}

    async def compact(self, params):  # noqa: ARG002 — protocol stub
        return {"ok": True, "compacted": False}


def _create_engine(required_capabilities):
    """Build a duck-typed ContextEngine with the supplied capability list.

    Mirrors the TypeScript ``createEngine`` helper.
    """
    return _Engine(required_capabilities)


def test_allows_engines_with_no_host_requirements():
    """A engine with ``[]`` required capabilities is always allowed."""
    assert_context_engine_host_support(
        context_engine=_create_engine([]),
        operation="agent-run",
        host=build_generic_cli_context_engine_host_support(backend_id="claude-cli"),
    )


def test_rejects_generic_cli_hosts_when_an_engine_requires_pre_prompt_assembly():
    """Generic CLI hosts lack ``assemble-before-prompt``; engines that
    require it should fail loud with a clear error message."""
    engine = _create_engine(["assemble-before-prompt"])
    host = build_generic_cli_context_engine_host_support(backend_id="claude-cli")
    with pytest.raises(
        RuntimeError,
        match=(
            r'Context engine "lossless-claw" cannot run operation "agent-run" '
            r'on CLI backend "claude-cli".'
        ),
    ):
        assert_context_engine_host_support(
            context_engine=engine, operation="agent-run", host=host
        )


def test_evaluates_missing_capabilities_without_throwing():
    """``evaluate`` returns the failure shape instead of raising."""
    engine = _create_engine(["assemble-before-prompt"])
    evaluation = evaluate_context_engine_host_support(
        context_engine_info=engine.info,
        operation="agent-run",
        host=build_generic_cli_context_engine_host_support(backend_id="claude-cli"),
    )

    assert evaluation["ok"] is False
    assert evaluation["missingCapabilities"] == ["assemble-before-prompt"]


def test_allows_native_codex_and_openclaw_embedded_hosts_to_satisfy_pre_prompt_assembly():
    """Both native hosts advertise ``assemble-before-prompt`` and pass."""
    engine = _create_engine(["assemble-before-prompt"])
    assert_context_engine_host_support(
        context_engine=engine,
        operation="agent-run",
        host=CODEX_APP_SERVER_CONTEXT_ENGINE_HOST,
    )
    assert_context_engine_host_support(
        context_engine=engine,
        operation="agent-run",
        host=OPENCLAW_EMBEDDED_CONTEXT_ENGINE_HOST,
    )


def test_allows_native_codex_to_satisfy_thread_bootstrap_projection():
    """Codex is the only host that advertises ``thread-bootstrap-projection``."""
    assert_context_engine_host_support(
        context_engine=_create_engine(
            ["assemble-before-prompt", "thread-bootstrap-projection"]
        ),
        operation="agent-run",
        host=CODEX_APP_SERVER_CONTEXT_ENGINE_HOST,
    )
