"""Phase 5.12b — ``runtime-settings.test.ts`` → Python.

OpenClaw parity: ports the 6 ``it`` blocks from
``src/context-engine/runtime-settings.test.ts``.

Python adaptations:
- ``contextEngineHost: OPENCLAW_EMBEDDED_CONTEXT_ENGINE_HOST`` becomes
  ``contextEngineHost=OPENCLAW_EMBEDDED_CONTEXT_ENGINE_HOST`` (the
  Python value is the same dict shape — ``id`` / ``label`` /
  ``capabilities`` keys).
- ``toMatchObject`` becomes a per-key ``assertEqual`` on the
  equivalent nested fields (the Python port doesn't have a
  drop-in ``toMatchObject`` helper).
- ``toEqual`` becomes a recursive ``assertEqual`` (``==`` already
  does deep equality for plain dicts/lists in Python).
- 128_000 → 128000 (no numeric separator in Python <3.6; we
  use the integer literal directly).
"""
from __future__ import annotations

from src.context_engine.host_compat import OPENCLAW_EMBEDDED_CONTEXT_ENGINE_HOST
from src.context_engine.runtime_settings import build_context_engine_runtime_settings


def test_builds_declared_normal_runtime_settings_from_host_and_model_inputs():
    settings = build_context_engine_runtime_settings(
        {
            "contextEngineHost": OPENCLAW_EMBEDDED_CONTEXT_ENGINE_HOST,
            "harnessId": "embedded",
            "runtimeId": "direct",
            "provider": "openai",
            "requestedModel": "gpt-5.5",
            "resolvedModel": "gpt-5.5",
            "selectedContextEngineId": "hypermem",
            "contextEngineSelectionSource": "configured",
            "promptTokenBudget": 128000,
            "maxOutputTokens": 8192,
        }
    )

    assert settings["schemaVersion"] == 1
    assert settings["runtime"] == {
        "host": "openclaw",
        "mode": "normal",
        "harnessId": "embedded",
        "runtimeId": "direct",
    }
    assert settings["model"] == {
        "requested": "gpt-5.5",
        "resolved": "gpt-5.5",
        "provider": "openai",
        "family": None,
    }
    assert settings["contextEngineSelection"] == {
        "selectedId": "hypermem",
        "source": "configured",
    }
    assert settings["executionHost"] == {
        "id": OPENCLAW_EMBEDDED_CONTEXT_ENGINE_HOST["id"],
        "label": OPENCLAW_EMBEDDED_CONTEXT_ENGINE_HOST["label"],
    }
    assert settings["limits"] == {
        "promptTokenBudget": 128000,
        "maxOutputTokens": 8192,
    }
    assert settings["diagnostics"] == {
        "fallbackReason": None,
        "degradedReason": None,
    }


def test_marks_fallback_mode_when_a_fallback_reason_is_present():
    settings = build_context_engine_runtime_settings(
        {
            "contextEngineHost": OPENCLAW_EMBEDDED_CONTEXT_ENGINE_HOST,
            "resolvedModel": "gpt-5-mini",
            "fallbackReason": "primary_unavailable",
        }
    )

    assert settings["runtime"]["mode"] == "fallback"
    assert settings["diagnostics"]["fallbackReason"] == "provider_unavailable"


def test_preserves_known_fallback_reason_codes():
    settings = build_context_engine_runtime_settings(
        {
            "contextEngineHost": OPENCLAW_EMBEDDED_CONTEXT_ENGINE_HOST,
            "resolvedModel": "gpt-5-mini",
            "fallbackReason": "provider_timeout",
        }
    )

    assert settings["runtime"]["mode"] == "fallback"
    assert settings["diagnostics"]["fallbackReason"] == "provider_timeout"


def test_marks_fallback_mode_when_resolved_model_differs_from_requested_model():
    settings = build_context_engine_runtime_settings(
        {
            "contextEngineHost": OPENCLAW_EMBEDDED_CONTEXT_ENGINE_HOST,
            "requestedModel": "openai/gpt-5.5",
            "resolvedModel": "anthropic/claude-sonnet-4-6",
        }
    )

    assert settings["runtime"]["mode"] == "fallback"
    assert settings["diagnostics"]["fallbackReason"] is None


def test_marks_degraded_mode_when_a_degraded_reason_is_present():
    settings = build_context_engine_runtime_settings(
        {
            "contextEngineHost": OPENCLAW_EMBEDDED_CONTEXT_ENGINE_HOST,
            "resolvedModel": "gpt-5-mini",
            "degradedReason": "context_pressure_high",
        }
    )

    assert settings["runtime"]["mode"] == "degraded"
    assert settings["diagnostics"]["degradedReason"] == "context_overflow"


def test_keeps_host_and_selection_ids_nullable_when_unknown():
    settings = build_context_engine_runtime_settings(
        {
            "contextEngineHost": {
                **OPENCLAW_EMBEDDED_CONTEXT_ENGINE_HOST,
                "id": "",
            },
        }
    )

    assert settings["contextEngineSelection"] == {
        "selectedId": None,
        "source": "unknown",
    }
    assert settings["executionHost"]["id"] is None
