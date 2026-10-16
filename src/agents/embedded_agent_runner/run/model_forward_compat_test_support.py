"""Test-support helpers for model forward compatibility.

This mirrors `openclaw-main/src/agents/embedded-agent-runner/model.forward-compat.test-support.ts`.
"""
from __future__ import annotations

from typing import Any, Dict


def build_forward_compat_template(params: Dict[str, Any]) -> Dict[str, Any]:
    """Build a forward-compat template model row for tests."""
    result: Dict[str, Any] = {
        "id": params["id"],
        "name": params["name"],
        "provider": params["provider"],
        "api": params["api"],
        "baseUrl": params["baseUrl"],
        "reasoning": params.get("reasoning", True),
        "input": params.get("input", ["text", "image"]),
        "cost": params.get(
            "cost",
            {"input": 5, "output": 25, "cacheRead": 0.5, "cacheWrite": 6.25},
        ),
        "contextWindow": params.get("contextWindow", 200000),
        "maxTokens": params.get("maxTokens", 64000),
    }
    return result


def expect_resolved_forward_compat_fallback_result(
    result: Dict[str, Any], expected_model: Dict[str, Any]
) -> None:
    """Assert a resolved forward-compat fallback result contains the expected model."""
    assert result.get("error") is None, f"unexpected error: {result.get('error')}"
    expect_model_fields(result.get("model"), expected_model)


def expect_resolved_forward_compat_fallback_with_registry_result(
    result: Any, expected_model: Dict[str, Any]
) -> None:
    """Assert a registry-backed forward-compat fallback result contains expected fields."""
    expect_model_fields(result, expected_model)


def expect_unknown_model_error_result(
    result: Dict[str, Any], provider: str, model_id: str
) -> None:
    """Assert the result is an unknown-model error for the requested provider/model."""
    assert result.get("model") is None
    assert result.get("error") == f"Unknown model: {provider}/{model_id}"


def expect_model_fields(actual: Any, expected: Dict[str, Any]) -> None:
    """Compare actual model fields against expected values."""
    assert isinstance(actual, dict), f"expected model dict, got {type(actual).__name__}"
    for key, value in expected.items():
        assert actual.get(key) == value, f"model field {key} differs: {actual.get(key)!r} != {value!r}"


__all__ = [
    "build_forward_compat_template",
    "expect_resolved_forward_compat_fallback_result",
    "expect_resolved_forward_compat_fallback_with_registry_result",
    "expect_unknown_model_error_result",
]
