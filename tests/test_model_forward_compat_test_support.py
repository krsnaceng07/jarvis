from src.agents.embedded_agent_runner.run.model_forward_compat_test_support import (
    build_forward_compat_template,
    expect_model_fields,
    expect_resolved_forward_compat_fallback_with_registry_result,
    expect_unknown_model_error_result,
)


def test_build_forward_compat_template_defaults() -> None:
    result = build_forward_compat_template(
        {
            "id": "gpt-5.4",
            "name": "GPT-5.4",
            "provider": "openai",
            "api": "openai-completions",
            "baseUrl": "https://api.openai.com",
        }
    )
    assert result["id"] == "gpt-5.4"
    assert result["provider"] == "openai"
    assert result["reasoning"] is True
    assert result["input"] == ["text", "image"]


def test_expect_unknown_model_error_result() -> None:
    result = {"error": "Unknown model: openai/gpt-5.3", "model": None}
    expect_unknown_model_error_result(result, "openai", "gpt-5.3")
