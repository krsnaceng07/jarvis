"""Test-only helpers for resetting context-engine quarantine state.

OpenClaw parity: ``src/context-engine/registry.test-support.ts``.
"""
from __future__ import annotations

import os

from src.shared.global_singleton import resolve_global_singleton

from .quarantine_health import clear_persisted_context_engine_quarantine_for_process

CONTEXT_ENGINE_REGISTRY_STATE = "openclaw.contextEngineRegistryState"


def reset_context_engine_runtime_quarantine_for_tests() -> None:
    state = resolve_global_singleton(
        CONTEXT_ENGINE_REGISTRY_STATE,
        lambda: {"engines": {}, "quarantinedEngines": {}},
    )
    state["quarantinedEngines"].clear()
    clear_persisted_context_engine_quarantine_for_process(None, os.getpid())
