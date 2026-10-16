"""Tests for the Codex compaction doctor migration (pure scan/apply).

OpenClaw parity: ``openclaw-main/src/commands/doctor/shared/codex-route-compaction-scan.ts``
(``collectUnsupportedCodexCompactionOverrides``,
``collectLegacyLosslessCompactionConfigs``) and
``codex-route-compaction-repair.ts`` (``removeUnsupportedCodexCompactionOverrides``:
``Removed <path>; Codex runtime uses native server-side compaction.``).
"""

from __future__ import annotations

from src.config.codex_compaction_migration import (
    apply_codex_compaction_repairs,
    collect_codex_compaction_repairs,
)


def _codex_agent_config(**agent_overrides):
    agent = {"id": "main", "model": "openai/gpt-5.6-sol"}
    agent.update(agent_overrides)
    return {
        "models": {"providers": {"openai": {"agentRuntime": {"id": "codex"}}}},
        "plugins": {"entries": {"codex": {"enabled": True}}},
        "agents": {"defaults": agent},
    }


def test_removes_unsupported_overrides_on_codex_agent():
    cfg = _codex_agent_config(compaction={"model": "openai/gpt-5.4", "provider": "custom"})
    repairs = collect_codex_compaction_repairs(cfg, {})
    assert {(h["path"], h["key"]) for h in repairs["remove"]} == {
        ("agents.defaults.compaction.model", "model"),
        ("agents.defaults.compaction.provider", "provider"),
    }
    assert repairs["lossless_warn"] == []
    changes = apply_codex_compaction_repairs(cfg, {})
    assert changes == [
        "Removed agents.defaults.compaction.model; Codex runtime uses native server-side compaction.",
        "Removed agents.defaults.compaction.provider; Codex runtime uses native server-side compaction.",
    ]
    assert "compaction" not in cfg["agents"]["defaults"]


def test_keeps_unrelated_compaction_keys():
    cfg = _codex_agent_config(compaction={"model": "x", "mode": "trim", "reserveTokens": 100})
    apply_codex_compaction_repairs(cfg, {})
    assert cfg["agents"]["defaults"]["compaction"] == {"mode": "trim", "reserveTokens": 100}


def test_non_codex_agent_untouched():
    cfg = {
        "agents": {
            "defaults": {
                "model": "anthropic/claude-opus-4-6",
                "compaction": {"model": "anthropic/x", "provider": "custom"},
            }
        }
    }
    assert collect_codex_compaction_repairs(cfg, {}) == {"remove": [], "lossless_warn": []}
    assert apply_codex_compaction_repairs(cfg, {}) == []


def test_implicit_codex_route_counts_as_codex():
    cfg = {
        "models": {
            "providers": {
                "openai": {"api": "openai-responses", "baseUrl": "https://api.openai.com/v1"}
            }
        },
        "agents": {
            "defaults": {
                "model": "openai/gpt-5.5",
                "compaction": {"model": "openai/gpt-5.4-mini"},
            }
        },
    }
    repairs = collect_codex_compaction_repairs(cfg, {})
    assert [h["path"] for h in repairs["remove"]] == ["agents.defaults.compaction.model"]


def test_inherited_defaults_compaction_points_at_defaults():
    cfg = {
        "models": {"providers": {"openai": {"agentRuntime": {"id": "codex"}}}},
        "agents": {
            "defaults": {"model": "openai/gpt-5.6-sol", "compaction": {"provider": "custom"}},
            "list": [{"id": "writer", "model": "openai/gpt-5.6-sol"}],
        },
    }
    repairs = collect_codex_compaction_repairs(cfg, {})
    assert [h["path"] for h in repairs["remove"]] == ["agents.defaults.compaction.provider"]
    changes = apply_codex_compaction_repairs(cfg, {})
    assert len(changes) == 1
    assert "compaction" not in cfg["agents"]["defaults"]
    assert "compaction" not in cfg["agents"]["list"][0]


def test_lossless_provider_warns_without_migrating():
    cfg = _codex_agent_config(
        compaction={"provider": "lossless-claw", "model": "openai/gpt-5.4-mini"}
    )
    repairs = collect_codex_compaction_repairs(cfg, {})
    assert repairs["remove"] == []
    assert len(repairs["lossless_warn"]) == 1
    hit = repairs["lossless_warn"][0]
    assert hit["provider_path"] == "agents.defaults.compaction.provider"
    assert hit["model_path"] == "agents.defaults.compaction.model"
    # No lossless extension ships: apply must not rewrite the slot.
    assert apply_codex_compaction_repairs(cfg, {}) == []
    assert cfg["agents"]["defaults"]["compaction"]["provider"] == "lossless-claw"


def test_list_entry_local_compaction_path():
    cfg = {
        "models": {"providers": {"openai": {"agentRuntime": {"id": "codex"}}}},
        "agents": {
            "defaults": {"model": "openai/gpt-5.6-sol"},
            "list": [
                {
                    "id": "writer",
                    "model": "openai/gpt-5.6-sol",
                    "compaction": {"model": "openai/x"},
                }
            ],
        },
    }
    assert [h["path"] for h in collect_codex_compaction_repairs(cfg, {})["remove"]] == [
        "agents.list.0.compaction.model"
    ]
    apply_codex_compaction_repairs(cfg, {})
    assert "compaction" not in cfg["agents"]["list"][0]


def test_collect_does_not_mutate():
    import copy

    cfg = _codex_agent_config(compaction={"model": "x"})
    snapshot = copy.deepcopy(cfg)
    collect_codex_compaction_repairs(cfg, {})
    assert cfg == snapshot
