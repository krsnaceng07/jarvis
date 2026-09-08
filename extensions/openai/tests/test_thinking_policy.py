"""Tests for the OpenAI provider-owned thinking policy.

OpenClaw parity: ``openclaw-main/extensions/openai/thinking-policy.ts``
plus the reasoning-effort table in ``model-route-contract.ts``.
"""

from __future__ import annotations

from extensions.openai.thinking_policy import (
    resolve_openai_codex_reasoning_efforts,
    resolve_thinking_profile,
    resolve_unified_openai_thinking_profile,
)


def _ids(profile):
    return [level["id"] for level in profile["levels"]]


def test_astra_uses_manifest_efforts_with_ultra():
    compat = {"supportedReasoningEfforts": ["low", "medium", "high", "xhigh", "max"]}
    profile = resolve_unified_openai_thinking_profile("gpt-6-astra", "openclaw", compat, None)
    assert _ids(profile) == ["off", "low", "medium", "high", "xhigh", "max", "ultra"]


def test_astra_without_efforts_stays_minimal():
    # No manifest catalog or compat metadata: only "off" is a valid choice.
    profile = resolve_unified_openai_thinking_profile("gpt-6-astra", "openclaw", None, None)
    assert _ids(profile) == ["off"]


def test_gpt56_sol_openclaw_has_max_ultra_and_medium_default():
    # xhigh arrives via prefix match on gpt-5.6; ultra on openclaw/auto is
    # OpenClaw-owned orchestration (thinking-policy.ts supportsUltra).
    profile = resolve_unified_openai_thinking_profile("gpt-5.6-sol", "openclaw", None, None)
    ids = _ids(profile)
    assert ids == ["off", "minimal", "low", "medium", "high", "xhigh", "max", "ultra"]
    assert profile["defaultLevel"] == "medium"


def test_gpt56_luna_openclaw_matches_sol():
    # Known 5.6 variant on the embedded runtime: same orchestration as sol.
    profile = resolve_unified_openai_thinking_profile("gpt-5.6-luna", "openclaw", None, None)
    assert _ids(profile) == ["off", "minimal", "low", "medium", "high", "xhigh", "max", "ultra"]
    assert profile["defaultLevel"] == "medium"


def test_gpt56_luna_codex_uses_native_efforts():
    # Native route: luna's catalog efforts (no ultra) bound the surface.
    profile = resolve_unified_openai_thinking_profile("gpt-5.6-luna", "codex", None, None)
    assert _ids(profile) == ["off", "low", "medium", "high", "xhigh", "max"]
    assert profile["defaultLevel"] == "medium"


def test_gpt55_gets_xhigh_on_unified_surface():
    profile = resolve_unified_openai_thinking_profile("gpt-5.5", "openclaw", None, None)
    assert "xhigh" in _ids(profile)
    assert "ultra" not in _ids(profile)


def test_unknown_model_keeps_base_levels():
    profile = resolve_unified_openai_thinking_profile("gpt-9.9", "openclaw", None, None)
    assert _ids(profile) == ["off", "minimal", "low", "medium", "high"]
    assert "defaultLevel" not in profile


def test_surface_rejects_non_openai_providers():
    assert resolve_thinking_profile({"provider": "anthropic", "modelId": "x"}) is None
    assert resolve_thinking_profile(None) is None


def test_surface_answers_openai():
    profile = resolve_thinking_profile(
        {"provider": "openai", "modelId": "gpt-5.6-sol", "agentRuntime": "openclaw"}
    )
    assert profile is not None
    assert "ultra" in _ids(profile)


def test_reasoning_efforts_merge_observations():
    assert resolve_openai_codex_reasoning_efforts("gpt-5.6-sol", None) == [
        "low",
        "medium",
        "high",
        "xhigh",
        "max",
        "ultra",
    ]
    # Partial observations cannot erase known capabilities; unknown extras
    # survive appended in first-seen order.
    assert resolve_openai_codex_reasoning_efforts("gpt-5.6-luna", ["low", "turbo"]) == [
        "low",
        "medium",
        "high",
        "xhigh",
        "max",
        "turbo",
    ]
    assert resolve_openai_codex_reasoning_efforts("gpt-9.9", ["low"]) == ["low"]
    assert resolve_openai_codex_reasoning_efforts("gpt-9.9", None) is None
    assert resolve_openai_codex_reasoning_efforts("gpt-5.6-sol", []) == []
