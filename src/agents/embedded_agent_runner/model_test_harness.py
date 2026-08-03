"""jarvis.agents.embedded_agent_runner.model_test_harness — shared model fixtures for tests.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/model.test-harness.ts``.

Public surface:

- :func:`make_model`
- :data:`OPENAI_CODEX_TEMPLATE_MODEL`
- :func:`mock_openai_codex_template_model`
- :func:`build_openai_codex_forward_compat_expectation`
- :func:`mock_discovered_model`
- :func:`reset_mock_discover_models`

Phase 7.6h-3 — focused minimal port.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional


def make_model(model_id: str) -> Dict[str, Any]:
    """Smallest valid model row used when tests only care about provider routing."""
    return {
        "id": model_id,
        "name": model_id,
        "reasoning": False,
        "input": ["text"],
        "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0},
        "contextWindow": 1,
        "maxTokens": 1,
    }


OPENAI_CODEX_TEMPLATE_MODEL: Dict[str, Any] = {
    "id": "gpt-5.3-codex",
    "name": "GPT-5.3 Codex",
    "provider": "openai",
    "api": "openai-chatgpt-responses",
    "baseUrl": "https://chatgpt.com/backend-api",
    "reasoning": True,
    "input": ["text", "image"],
    "cost": {"input": 2.5, "output": 15, "cacheRead": 0.25, "cacheWrite": 0},
    "contextWindow": 1_050_000,
    "contextTokens": 272_000,
    "maxTokens": 128_000,
}


def _mock_template_model(
    discover_models_mock: Callable,
    provider: str,
    model_id: str,
    template_model: Any,
) -> None:
    mock_discovered_model(
        discover_models_mock,
        {"provider": provider, "modelId": model_id, "templateModel": template_model},
    )


def mock_openai_codex_template_model(discover_models_mock: Callable) -> None:
    _mock_template_model(
        discover_models_mock,
        "openai",
        OPENAI_CODEX_TEMPLATE_MODEL["id"],
        OPENAI_CODEX_TEMPLATE_MODEL,
    )


def build_openai_codex_forward_compat_expectation(
    model_id: str = "gpt-5.3-codex",
) -> Dict[str, Any]:
    is_gpt54 = model_id == "gpt-5.4"
    is_gpt55 = model_id == "gpt-5.5"
    is_gpt54_mini = model_id == "gpt-5.4-mini"
    is_spark = model_id == "gpt-5.3-codex-spark"
    if is_spark:
        cost: Dict[str, float] = {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0}
    elif is_gpt54:
        cost = {"input": 2.5, "output": 15, "cacheRead": 0.25, "cacheWrite": 0}
    elif is_gpt54_mini:
        cost = {"input": 0.75, "output": 4.5, "cacheRead": 0.075, "cacheWrite": 0}
    else:
        cost = OPENAI_CODEX_TEMPLATE_MODEL["cost"]
    context_window = (
        1_050_000
        if is_gpt54
        else 400_000
        if is_gpt55 or is_gpt54_mini
        else 128_000
        if is_spark
        else 272_000
    )
    result: Dict[str, Any] = {
        "provider": "openai",
        "id": model_id,
        "api": "openai-chatgpt-responses",
        "baseUrl": "https://chatgpt.com/backend-api",
        "reasoning": True,
        "input": ["text"] if is_spark else ["text", "image"],
        "cost": cost,
        "contextWindow": context_window,
        "maxTokens": 128_000,
    }
    if is_gpt54 or is_gpt55 or is_gpt54_mini:
        result["contextTokens"] = 272_000
    return result


def reset_mock_discover_models(discover_models_mock: Callable) -> None:
    def _find(_p: str, _m: str):
        return None
    discover_models_mock.return_value = {"find": _find}


def mock_discovered_model(
    discover_models_mock: Callable,
    params: Dict[str, Any],
) -> None:
    provider = params["provider"]
    model_id = params["modelId"]
    template_model = params["templateModel"]

    def _find(p: str, m: str):
        if p == provider and m == model_id:
            return template_model
        return None

    discover_models_mock.return_value = {"find": _find}


__all__ = [
    "make_model",
    "OPENAI_CODEX_TEMPLATE_MODEL",
    "mock_openai_codex_template_model",
    "build_openai_codex_forward_compat_expectation",
    "mock_discovered_model",
    "reset_mock_discover_models",
]
