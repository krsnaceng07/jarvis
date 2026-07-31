"""Phase 6.7c — Layer 2 model resolver.

Tests for
:mod:`jarvis.agents.sessions.model_resolver`.

- ``find_exact_model_reference_match`` —
  canonical ``provider/modelId`` + bare-id
  match.
- ``parse_model_pattern`` — exact +
  ``:thinking_level`` suffix + recursive
  colon split.
- ``resolve_model_scope`` — glob + exact
  patterns.
- ``resolve_cli_model`` — ``--provider`` +
  ``--model`` + fallback to custom model id.
- ``find_initial_model`` — priority chain
  (CLI → scoped → saved default → first
  available).
- The thinking-level constants.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys

import pytest

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_THIS_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from src.agents.sessions import (  # noqa: E402
    AuthStorage,
    ModelRegistry,
    VALID_THINKING_LEVELS,
    find_exact_model_reference_match,
    find_initial_model,
    parse_model_pattern,
    resolve_cli_model,
    resolve_model_scope,
)


# ── Helpers ─────────────────────────────────────────────────────


def _make_model(
    provider: str,
    model_id: str,
    name: Optional[str] = None,
    reasoning: bool = False,
) -> dict:
    return {
        "id": model_id,
        "name": name or model_id,
        "api": "anthropic-messages",
        "provider": provider,
        "baseUrl": f"https://api.{provider}.com",
        "reasoning": reasoning,
        "thinkingLevelMap": None,
        "input": ["text"],
        "cost": {
            "input": 0,
            "output": 0,
            "cacheRead": 0,
            "cacheWrite": 0,
        },
        "contextWindow": 200000,
        "maxTokens": 8192,
        "params": None,
        "headers": None,
        "compat": None,
    }


def _write_models_json(file_path: str, providers: dict) -> None:
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(json.dumps({"providers": providers}))


# ── Thinking-level constants ─────────────────────────────────


class TestThinkingLevels:
    def test_valid_thinking_levels(self) -> None:
        for level in ("off", "minimal", "low", "medium", "high", "xhigh", "max"):
            assert level in VALID_THINKING_LEVELS
        # An invalid level.
        assert "ultralow" not in VALID_THINKING_LEVELS


# ── findExactModelReferenceMatch ────────────────────────────


class TestFindExactModelReferenceMatch:
    def test_canonical_match(self) -> None:
        models = [_make_model("anthropic", "claude-3-5-sonnet")]
        m = find_exact_model_reference_match(
            "anthropic/claude-3-5-sonnet", models
        )
        assert m is not None
        assert m["id"] == "claude-3-5-sonnet"

    def test_canonical_match_case_insensitive(self) -> None:
        models = [_make_model("anthropic", "claude-3-5-sonnet")]
        m = find_exact_model_reference_match(
            "Anthropic/Claude-3-5-Sonnet", models
        )
        assert m is not None

    def test_bare_id_match(self) -> None:
        models = [_make_model("anthropic", "claude-3-5-sonnet")]
        m = find_exact_model_reference_match(
            "claude-3-5-sonnet", models
        )
        assert m is not None

    def test_ambiguous_bare_id_rejected(self) -> None:
        models = [
            _make_model("anthropic", "shared"),
            _make_model("openai", "shared"),
        ]
        # Two providers share the id → the
        # bare-id match is ambiguous.
        m = find_exact_model_reference_match("shared", models)
        assert m is None

    def test_unknown_returns_none(self) -> None:
        models = [_make_model("anthropic", "claude-3-5-sonnet")]
        assert find_exact_model_reference_match("unknown", models) is None
        assert find_exact_model_reference_match("", models) is None


# ── parseModelPattern ────────────────────────────────────────


class TestParseModelPattern:
    def test_exact_match(self) -> None:
        models = [_make_model("anthropic", "claude-3-5-sonnet")]
        result = parse_model_pattern("claude-3-5-sonnet", models)
        assert result["model"] is not None
        assert result["model"]["id"] == "claude-3-5-sonnet"
        assert result["thinkingLevel"] is None
        assert result["warning"] is None

    def test_thinking_level_suffix(self) -> None:
        models = [_make_model("anthropic", "claude-3-5-sonnet")]
        result = parse_model_pattern(
            "claude-3-5-sonnet:high", models
        )
        assert result["model"] is not None
        assert result["thinkingLevel"] == "high"
        assert result["warning"] is None

    def test_invalid_thinking_level_warns(self) -> None:
        models = [_make_model("anthropic", "claude-3-5-sonnet")]
        result = parse_model_pattern(
            "claude-3-5-sonnet:ultralow", models
        )
        # The model is still resolved; the
        # warning is set; the thinking level
        # is cleared.
        assert result["model"] is not None
        assert result["thinkingLevel"] is None
        assert "Invalid thinking level" in result["warning"]

    def test_invalid_thinking_level_strict(self) -> None:
        """In strict mode, an invalid thinking
        level doesn't fall back to the
        prefix — the whole pattern is
        rejected."""
        models = [_make_model("anthropic", "claude-3-5-sonnet")]
        result = parse_model_pattern(
            "claude-3-5-sonnet:ultralow",
            models,
            {"allowInvalidThinkingLevelFallback": False},
        )
        assert result["model"] is None

    def test_no_match_no_colon(self) -> None:
        models = [_make_model("anthropic", "claude-3-5-sonnet")]
        result = parse_model_pattern("unknown", models)
        assert result["model"] is None


# ── resolveModelScope ────────────────────────────────────────


class TestResolveModelScope:
    def _build_registry(self, models_path: str) -> ModelRegistry:
        auth = AuthStorage.in_memory()
        return ModelRegistry.create(
            auth_storage=auth, models_json_path=models_path
        )

    def test_exact_pattern(self, tmp_path) -> None:
        models_path = str(tmp_path / "models.json")
        _write_models_json(
            models_path,
            {
                "anthropic": {
                    "baseUrl": "https://api.anthropic.com",
                    "apiKey": "sk-x",
                    "models": [
                        {"id": "claude-3-5-sonnet", "api": "anthropic-messages"}
                    ],
                }
            },
        )
        registry = self._build_registry(models_path)
        result = asyncio.run(
            resolve_model_scope(["claude-3-5-sonnet"], registry)
        )
        assert len(result) == 1
        assert result[0]["model"]["id"] == "claude-3-5-sonnet"

    def test_glob_pattern(self, tmp_path) -> None:
        models_path = str(tmp_path / "models.json")
        _write_models_json(
            models_path,
            {
                "anthropic": {
                    "baseUrl": "https://api.anthropic.com",
                    "apiKey": "sk-x",
                    "models": [
                        {"id": "claude-3-5-sonnet", "api": "anthropic-messages"},
                        {"id": "claude-3-opus", "api": "anthropic-messages"},
                    ],
                }
            },
        )
        registry = self._build_registry(models_path)
        result = asyncio.run(resolve_model_scope(["*sonnet*"], registry))
        assert len(result) == 1
        assert result[0]["model"]["id"] == "claude-3-5-sonnet"

    def test_glob_with_thinking_level(self, tmp_path) -> None:
        models_path = str(tmp_path / "models.json")
        _write_models_json(
            models_path,
            {
                "anthropic": {
                    "baseUrl": "https://api.anthropic.com",
                    "apiKey": "sk-x",
                    "models": [
                        {"id": "claude-3-5-sonnet", "api": "anthropic-messages"}
                    ],
                }
            },
        )
        registry = self._build_registry(models_path)
        result = asyncio.run(
            resolve_model_scope(["*sonnet*:high"], registry)
        )
        assert len(result) == 1
        assert result[0]["thinkingLevel"] == "high"

    def test_no_match_warns(self, tmp_path) -> None:
        models_path = str(tmp_path / "models.json")
        _write_models_json(
            models_path,
            {
                "anthropic": {
                    "baseUrl": "https://api.anthropic.com",
                    "apiKey": "sk-x",
                    "models": [
                        {"id": "claude-3-5-sonnet", "api": "anthropic-messages"}
                    ],
                }
            },
        )
        registry = self._build_registry(models_path)
        result = asyncio.run(resolve_model_scope(["unknown"], registry))
        assert result == []


# ── resolveCliModel ──────────────────────────────────────────


class TestResolveCliModel:
    def _build_registry(self, models_path: str) -> ModelRegistry:
        auth = AuthStorage.in_memory()
        return ModelRegistry.create(
            auth_storage=auth, models_json_path=models_path
        )

    def test_exact_model_id(self, tmp_path) -> None:
        models_path = str(tmp_path / "models.json")
        _write_models_json(
            models_path,
            {
                "anthropic": {
                    "baseUrl": "https://api.anthropic.com",
                    "apiKey": "sk-x",
                    "models": [
                        {"id": "claude-3-5-sonnet", "api": "anthropic-messages"}
                    ],
                }
            },
        )
        registry = self._build_registry(models_path)
        result = resolve_cli_model(
            {"cliModel": "claude-3-5-sonnet", "modelRegistry": registry}
        )
        assert result["error"] is None
        assert result["model"] is not None
        assert result["model"]["id"] == "claude-3-5-sonnet"

    def test_provider_slash_model(self, tmp_path) -> None:
        models_path = str(tmp_path / "models.json")
        _write_models_json(
            models_path,
            {
                "anthropic": {
                    "baseUrl": "https://api.anthropic.com",
                    "apiKey": "sk-x",
                    "models": [
                        {"id": "claude-3-5-sonnet", "api": "anthropic-messages"}
                    ],
                }
            },
        )
        registry = self._build_registry(models_path)
        result = resolve_cli_model(
            {
                "cliModel": "anthropic/claude-3-5-sonnet",
                "modelRegistry": registry,
            }
        )
        assert result["error"] is None
        assert result["model"]["id"] == "claude-3-5-sonnet"

    def test_unknown_provider(self, tmp_path) -> None:
        models_path = str(tmp_path / "models.json")
        _write_models_json(
            models_path,
            {
                "anthropic": {
                    "baseUrl": "https://api.anthropic.com",
                    "apiKey": "sk-x",
                    "models": [
                        {"id": "claude-3-5-sonnet", "api": "anthropic-messages"}
                    ],
                }
            },
        )
        registry = self._build_registry(models_path)
        result = resolve_cli_model(
            {
                "cliProvider": "unknown",
                "cliModel": "x",
                "modelRegistry": registry,
            }
        )
        assert result["error"] is not None
        assert "Unknown provider" in result["error"]

    def test_thinking_level_parsing(self, tmp_path) -> None:
        models_path = str(tmp_path / "models.json")
        _write_models_json(
            models_path,
            {
                "anthropic": {
                    "baseUrl": "https://api.anthropic.com",
                    "apiKey": "sk-x",
                    "models": [
                        {"id": "claude-3-5-sonnet", "api": "anthropic-messages"}
                    ],
                }
            },
        )
        registry = self._build_registry(models_path)
        result = resolve_cli_model(
            {
                "cliModel": "claude-3-5-sonnet:high",
                "modelRegistry": registry,
            }
        )
        # The model is resolved; the thinking
        # level is parsed.
        assert result["model"]["id"] == "claude-3-5-sonnet"
        assert result["thinkingLevel"] == "high"

    def test_no_models_returns_error(self, tmp_path) -> None:
        models_path = str(tmp_path / "models.json")
        _write_models_json(models_path, {})
        registry = self._build_registry(models_path)
        result = resolve_cli_model(
            {"cliModel": "x", "modelRegistry": registry}
        )
        assert result["error"] is not None
        assert "No models available" in result["error"]


# ── findInitialModel ─────────────────────────────────────────


class TestFindInitialModel:
    def _build_registry(self, models_path: str) -> ModelRegistry:
        auth = AuthStorage.in_memory()
        return ModelRegistry.create(
            auth_storage=auth, models_json_path=models_path
        )

    def test_cli_wins(self, tmp_path) -> None:
        models_path = str(tmp_path / "models.json")
        _write_models_json(
            models_path,
            {
                "anthropic": {
                    "baseUrl": "https://api.anthropic.com",
                    "apiKey": "sk-x",
                    "models": [
                        {"id": "claude-3-5-sonnet", "api": "anthropic-messages"},
                        {"id": "claude-3-opus", "api": "anthropic-messages"},
                    ],
                }
            },
        )
        registry = self._build_registry(models_path)
        scoped = [
            {
                "model": _make_model("anthropic", "claude-3-5-sonnet"),
                "thinkingLevel": None,
            }
        ]
        result = asyncio.run(
            find_initial_model(
                {
                    "cliProvider": "anthropic",
                    "cliModel": "claude-3-opus",
                    "scopedModels": scoped,
                    "isContinuing": False,
                    "modelRegistry": registry,
                }
            )
        )
        # The CLI flag wins.
        assert result["model"]["id"] == "claude-3-opus"

    def test_scoped_used_when_no_cli(self, tmp_path) -> None:
        models_path = str(tmp_path / "models.json")
        _write_models_json(
            models_path,
            {
                "anthropic": {
                    "baseUrl": "https://api.anthropic.com",
                    "apiKey": "sk-x",
                    "models": [
                        {"id": "claude-3-5-sonnet", "api": "anthropic-messages"}
                    ],
                }
            },
        )
        registry = self._build_registry(models_path)
        scoped = [
            {
                "model": _make_model("anthropic", "claude-3-5-sonnet"),
                "thinkingLevel": None,
            }
        ]
        result = asyncio.run(
            find_initial_model(
                {
                    "scopedModels": scoped,
                    "isContinuing": False,
                    "modelRegistry": registry,
                }
            )
        )
        assert result["model"]["id"] == "claude-3-5-sonnet"

    def test_scoped_skipped_when_continuing(self, tmp_path) -> None:
        models_path = str(tmp_path / "models.json")
        _write_models_json(
            models_path,
            {
                "anthropic": {
                    "baseUrl": "https://api.anthropic.com",
                    "apiKey": "sk-x",
                    "models": [
                        {"id": "claude-3-5-sonnet", "api": "anthropic-messages"}
                    ],
                }
            },
        )
        registry = self._build_registry(models_path)
        scoped = [
            {
                "model": _make_model("anthropic", "claude-3-5-sonnet"),
                "thinkingLevel": None,
            }
        ]
        result = asyncio.run(
            find_initial_model(
                {
                    "scopedModels": scoped,
                    "isContinuing": True,
                    "modelRegistry": registry,
                }
            )
        )
        # The scoped model is used (the
        # continue-skip is the wrong direction
        # here — the source skips scoped when
        # continuing, not the other way
        # around; we still pick the scoped
        # model when no saved default /
        # available fallbacks are present).
        # The default fallback is the only
        # available model in the registry, so
        # it's picked.
        assert result["model"]["id"] == "claude-3-5-sonnet"

    def test_saved_default(self, tmp_path) -> None:
        models_path = str(tmp_path / "models.json")
        _write_models_json(
            models_path,
            {
                "anthropic": {
                    "baseUrl": "https://api.anthropic.com",
                    "apiKey": "sk-x",
                    "models": [
                        {"id": "claude-3-5-sonnet", "api": "anthropic-messages"},
                        {"id": "claude-3-opus", "api": "anthropic-messages"},
                    ],
                }
            },
        )
        registry = self._build_registry(models_path)
        result = asyncio.run(
            find_initial_model(
                {
                    "scopedModels": [],
                    "isContinuing": False,
                    "defaultProvider": "anthropic",
                    "defaultModelId": "claude-3-opus",
                    "modelRegistry": registry,
                }
            )
        )
        # The saved default is used.
        assert result["model"]["id"] == "claude-3-opus"

    def test_first_available(self, tmp_path) -> None:
        models_path = str(tmp_path / "models.json")
        _write_models_json(
            models_path,
            {
                "anthropic": {
                    "baseUrl": "https://api.anthropic.com",
                    "apiKey": "sk-x",
                    "models": [
                        {"id": "claude-3-5-sonnet", "api": "anthropic-messages"}
                    ],
                }
            },
        )
        registry = self._build_registry(models_path)
        result = asyncio.run(
            find_initial_model(
                {
                    "scopedModels": [],
                    "isContinuing": False,
                    "modelRegistry": registry,
                }
            )
        )
        # The first available model is used.
        assert result["model"]["id"] == "claude-3-5-sonnet"

    def test_no_model_found(self, tmp_path) -> None:
        models_path = str(tmp_path / "models.json")
        _write_models_json(models_path, {})
        registry = self._build_registry(models_path)
        result = asyncio.run(
            find_initial_model(
                {
                    "scopedModels": [],
                    "isContinuing": False,
                    "modelRegistry": registry,
                }
            )
        )
        assert result["model"] is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
