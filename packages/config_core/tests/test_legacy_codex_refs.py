"""Tests for legacy Codex model-ref doctor migration.

OpenClaw parity: ``openclaw-main/src/commands/doctor/shared/codex-route-model-ref.ts``
(``toCanonicalOpenAIModelRef``) + the ``should become`` warning shape in
``codex-route-warnings.test.ts`` (e.g. ``- agents.defaults.model:
openai-codex/gpt-5.5 should become openai/gpt-5.5.``).
"""

from __future__ import annotations

import json

import pytest

from jarvis_config_core.doctor import (
    apply_legacy_codex_model_refs,
    core_legacy_codex_refs_doctor_contract,
    detect_legacy_codex_model_refs,
)
from jarvis_config_core.legacy_codex import (
    is_legacy_codex_provider_id,
    to_canonical_openai_model_ref,
)


@pytest.mark.parametrize(
    ("provider", "expected"),
    [
        ("codex", True),
        ("openai-codex", True),
        ("CODEX", True),
        (" OpenAI-Codex ", True),
        ("openai", False),
        ("anthropic", False),
        ("", False),
        (None, False),
        (123, False),
    ],
)
def test_is_legacy_codex_provider_id(provider, expected):
    assert is_legacy_codex_provider_id(provider) is expected


@pytest.mark.parametrize(
    ("ref", "expected"),
    [
        # Doc example: legacy refs rewrite to openai/*.
        ("openai-codex/gpt-5.4", "openai/gpt-5.4"),
        ("openai-codex/gpt-5.5", "openai/gpt-5.5"),
        ("codex/gpt-5.5", "openai/gpt-5.5"),
        ("OpenAI-Codex/GPT-5.4", "openai/GPT-5.4"),  # model-id case preserved
        ("openai/gpt-5.5", None),
        ("anthropic/claude-opus-4-6", None),
        ("gpt-5.5", None),  # no provider prefix
        ("openai-codex:p1", None),  # live auth-profile namespace, not a ref
        ("openai-codex/", None),
        ("", None),
        (None, None),
    ],
)
def test_to_canonical_openai_model_ref(ref, expected):
    assert to_canonical_openai_model_ref(ref) == expected


def test_rewrites_top_level_and_agent_slots():
    from jarvis_config_core.doctor import _detect_and_migrate_legacy_codex_refs

    raw = {
        "model": "openai-codex/gpt-5.4",
        "agents": {
            "defaults": {"model": "codex/gpt-5.5"},
            "list": [{"id": "writer", "model": {"primary": "openai-codex/gpt-5.4"}}],
            "entries": {"helper": {"model": "openai/gpt-5.5"}},
        },
    }
    res = _detect_and_migrate_legacy_codex_refs(raw, apply=True)
    assert raw["model"] == "openai/gpt-5.4"
    assert raw["agents"]["defaults"]["model"] == "openai/gpt-5.5"
    assert raw["agents"]["list"][0]["model"]["primary"] == "openai/gpt-5.4"
    assert raw["agents"]["entries"]["helper"]["model"] == "openai/gpt-5.5"
    assert res["changes"] == [
        "- model: openai-codex/gpt-5.4 should become openai/gpt-5.4.",
        "- agents.defaults.model: codex/gpt-5.5 should become openai/gpt-5.5.",
        "- agents.list.0.model.primary: openai-codex/gpt-5.4 should become openai/gpt-5.4.",
    ]
    assert res["warnings"] == []
    assert res["has_findings"] is True


def test_split_provider_shape_rewrites_provider():
    from jarvis_config_core.doctor import _detect_and_migrate_legacy_codex_refs

    raw = {"agents": {"defaults": {"model": {"provider": "openai-codex", "model": "gpt-5.4"}}}}
    res = _detect_and_migrate_legacy_codex_refs(raw, apply=True)
    assert raw["agents"]["defaults"]["model"]["provider"] == "openai"
    assert res["changes"] == [
        "- agents.defaults.model.provider: openai-codex should become openai."
    ]


def test_image_slots_keep_codex_prefix_but_rewrite_openai_codex():
    from jarvis_config_core.doctor import _detect_and_migrate_legacy_codex_refs

    raw = {"visionModel": "codex/gpt-5.6-sol", "imageModel": "openai-codex/gpt-image-1"}
    res = _detect_and_migrate_legacy_codex_refs(raw, apply=True)
    # codex/ in image slots is the intentional bounded-turn signal: preserved.
    assert raw["visionModel"] == "codex/gpt-5.6-sol"
    # openai-codex/ is legacy everywhere: rewritten.
    assert raw["imageModel"] == "openai/gpt-image-1"
    assert res["changes"] == [
        "- imageModel: openai-codex/gpt-image-1 should become openai/gpt-image-1."
    ]


def test_media_and_utility_slots_in_agent_scopes():
    from jarvis_config_core.doctor import _detect_and_migrate_legacy_codex_refs

    raw = {
        "agents": {
            "defaults": {
                "utilityModel": "openai-codex/gpt-5.4",
                "imageGenerationModel": "openai-codex/gpt-image-1",
                "videoGenerationModel": "codex/sora-2",
            }
        }
    }
    res = _detect_and_migrate_legacy_codex_refs(raw, apply=True)
    defaults = raw["agents"]["defaults"]
    assert defaults["utilityModel"] == "openai/gpt-5.4"
    assert defaults["imageGenerationModel"] == "openai/gpt-image-1"
    assert defaults["videoGenerationModel"] == "codex/sora-2"
    assert res["changes"] == [
        "- agents.defaults.utilityModel: openai-codex/gpt-5.4 should become openai/gpt-5.4.",
        "- agents.defaults.imageGenerationModel: "
        "openai-codex/gpt-image-1 should become openai/gpt-image-1.",
    ]


def test_models_map_keys_rename_and_blocked_merge_warns():
    from jarvis_config_core.doctor import _detect_and_migrate_legacy_codex_refs

    raw = {
        "agents": {
            "defaults": {
                "models": {
                    "openai-codex/gpt-5.5": {"agentRuntime": {"id": "codex"}},
                    "openai/gpt-5.5": {"agentRuntime": {"id": "openclaw"}},
                    "openai-codex/gpt-5.4": {"params": {"temperature": 0.2}},
                }
            }
        }
    }
    res = _detect_and_migrate_legacy_codex_refs(raw, apply=True)
    models = raw["agents"]["defaults"]["models"]
    # Canonical already present: legacy entry preserved, warning recorded.
    assert models["openai-codex/gpt-5.5"] == {"agentRuntime": {"id": "codex"}}
    # Canonical absent: renamed with value intact.
    assert models["openai/gpt-5.4"] == {"params": {"temperature": 0.2}}
    assert "openai-codex/gpt-5.4" not in models
    assert res["changes"] == [
        "- agents.defaults.models.openai-codex/gpt-5.4: "
        "openai-codex/gpt-5.4 should become openai/gpt-5.4."
    ]
    assert len(res["warnings"]) == 1
    assert "openai-codex/gpt-5.5" in res["warnings"][0]


def test_allow_lists_rewrite():
    from jarvis_config_core.doctor import _detect_and_migrate_legacy_codex_refs

    raw = {"agents": {"list": [{"id": "w", "modelPolicy": {"allow": ["openai-codex/gpt-5.5"]}}]}}
    res = _detect_and_migrate_legacy_codex_refs(raw, apply=True)
    assert raw["agents"]["list"][0]["modelPolicy"]["allow"] == ["openai/gpt-5.5"]
    assert res["changes"] == [
        "- agents.list.0.modelPolicy.allow.0: openai-codex/gpt-5.5 should become openai/gpt-5.5."
    ]


def test_detect_only_leaves_config_untouched():
    from jarvis_config_core.doctor import _detect_and_migrate_legacy_codex_refs

    raw = {"model": "openai-codex/gpt-5.4"}
    res = _detect_and_migrate_legacy_codex_refs(raw, apply=False)
    assert raw["model"] == "openai-codex/gpt-5.4"
    assert res["has_findings"] is True


def test_clean_config_has_no_findings():
    from jarvis_config_core.doctor import _detect_and_migrate_legacy_codex_refs

    raw = {"model": "openai/gpt-5.5", "agents": {"defaults": {"model": "anthropic/x"}}}
    assert _detect_and_migrate_legacy_codex_refs(raw, apply=False)["has_findings"] is False


def test_legacy_provider_api_rewrites():
    from jarvis_config_core.doctor import _detect_and_migrate_legacy_codex_refs

    raw = {
        "models": {
            "providers": {
                "openai": {
                    "api": "openai-codex-responses",
                    "models": [
                        {"id": "gpt-5.5", "api": "openai-codex-responses"},
                        {"id": "gpt-5.4", "api": "openai-responses"},
                    ],
                }
            }
        }
    }
    res = _detect_and_migrate_legacy_codex_refs(raw, apply=True)
    provider = raw["models"]["providers"]["openai"]
    chatgpt_api = "openai-chatgpt-responses"
    assert provider["api"] == chatgpt_api
    assert provider["models"][0]["api"] == chatgpt_api
    assert provider["models"][1]["api"] == "openai-responses"
    assert res["changes"] == [
        'Moved models.providers.openai.api "openai-codex-responses" → "openai-chatgpt-responses".',
        'Moved models.providers.openai.models[0].api "openai-codex-responses" → '
        '"openai-chatgpt-responses".',
    ]
    # Detect-only leaves the file untouched.
    raw2 = {"models": {"providers": {"openai": {"api": "openai-codex-responses"}}}}
    res2 = _detect_and_migrate_legacy_codex_refs(raw2, apply=False)
    assert raw2["models"]["providers"]["openai"]["api"] == "openai-codex-responses"
    assert res2["has_findings"] is True


def test_nested_model_slots_rewrite():
    from jarvis_config_core.doctor import _detect_and_migrate_legacy_codex_refs

    raw = {
        "agents": {
            "defaults": {
                "model": "openai/gpt-5.5",
                "heartbeat": {"model": "openai-codex/gpt-5.4", "mode": "available"},
                "subagents": {"model": {"primary": "codex/gpt-5.5"}},
            }
        }
    }
    res = _detect_and_migrate_legacy_codex_refs(raw, apply=True)
    assert raw["agents"]["defaults"]["heartbeat"]["model"] == "openai/gpt-5.4"
    assert raw["agents"]["defaults"]["subagents"]["model"]["primary"] == "openai/gpt-5.5"
    assert raw["agents"]["defaults"]["heartbeat"]["mode"] == "available"
    assert res["changes"] == [
        "- agents.defaults.heartbeat.model: openai-codex/gpt-5.4 should become openai/gpt-5.4.",
        "- agents.defaults.subagents.model.primary: codex/gpt-5.5 should become openai/gpt-5.5.",
    ]


def test_contract_shape():
    assert core_legacy_codex_refs_doctor_contract["id"] == "core-config-legacy-codex-refs"
    assert core_legacy_codex_refs_doctor_contract["version"] == "1.0.0"
    assert callable(core_legacy_codex_refs_doctor_contract["detect"])
    assert callable(core_legacy_codex_refs_doctor_contract["apply"])


def test_detect_and_apply_wrappers_use_config_file(tmp_path, monkeypatch):
    import jarvis_config_core.doctor as doctor_mod

    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(
        json.dumps({"model": "openai-codex/gpt-5.4", "agents": {"defaults": {}}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(doctor_mod, "CONFIG_PATH", cfg_file)
    findings = detect_legacy_codex_model_refs(tmp_path, {})
    assert len(findings) == 1
    assert findings[0]["severity"] == "error"
    assert "openai-codex/gpt-5.4 should become openai/gpt-5.4" in findings[0]["message"]
    # File untouched by detect.
    assert json.loads(cfg_file.read_text(encoding="utf-8"))["model"] == "openai-codex/gpt-5.4"
    result = apply_legacy_codex_model_refs(tmp_path, {})
    assert len(result["changes"]) == 1
    assert json.loads(cfg_file.read_text(encoding="utf-8"))["model"] == "openai/gpt-5.4"
    # Second run is clean.
    assert detect_legacy_codex_model_refs(tmp_path, {}) == []


def test_wrappers_handle_missing_file(tmp_path, monkeypatch):
    import jarvis_config_core.doctor as doctor_mod

    monkeypatch.setattr(doctor_mod, "CONFIG_PATH", tmp_path / "nope.json")
    assert detect_legacy_codex_model_refs(tmp_path, {}) == []
    assert apply_legacy_codex_model_refs(tmp_path, {}) == {"changes": [], "warnings": []}
