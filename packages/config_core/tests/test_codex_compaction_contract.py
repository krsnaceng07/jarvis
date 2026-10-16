"""Tests for the core-config-codex-compaction doctor contract wiring."""

from __future__ import annotations

import json

from jarvis_config_core.doctor import (
    apply_codex_compaction_overrides,
    core_codex_compaction_doctor_contract,
    detect_codex_compaction_overrides,
)


def _write_config(path, raw):
    path.write_text(json.dumps(raw), encoding="utf-8")


def test_contract_shape():
    assert core_codex_compaction_doctor_contract["id"] == "core-config-codex-compaction"
    assert core_codex_compaction_doctor_contract["version"] == "1.0.0"
    assert callable(core_codex_compaction_doctor_contract["detect"])
    assert callable(core_codex_compaction_doctor_contract["apply"])


def test_detect_and_apply_round_trip(tmp_path, monkeypatch):
    import jarvis_config_core.doctor as doctor_mod

    cfg_file = tmp_path / "config.json"
    _write_config(
        cfg_file,
        {
            "models": {"providers": {"openai": {"agentRuntime": {"id": "codex"}}}},
            "agents": {
                "defaults": {
                    "model": "openai/gpt-5.6-sol",
                    "compaction": {"model": "openai/gpt-5.4", "mode": "trim"},
                }
            },
        },
    )
    monkeypatch.setattr(doctor_mod, "CONFIG_PATH", cfg_file)
    findings = detect_codex_compaction_overrides(tmp_path, {})
    assert len(findings) == 1
    assert findings[0]["severity"] == "error"
    assert "agents.defaults.compaction.model" in findings[0]["message"]
    result = apply_codex_compaction_overrides(tmp_path, {})
    assert len(result["changes"]) == 1
    assert "native server-side compaction" in result["changes"][0]
    raw = json.loads(cfg_file.read_text(encoding="utf-8"))
    assert raw["agents"]["defaults"]["compaction"] == {"mode": "trim"}
    assert detect_codex_compaction_overrides(tmp_path, {}) == []


def test_lossless_surfaces_warning(tmp_path, monkeypatch):
    import jarvis_config_core.doctor as doctor_mod

    cfg_file = tmp_path / "config.json"
    _write_config(
        cfg_file,
        {
            "models": {"providers": {"openai": {"agentRuntime": {"id": "codex"}}}},
            "agents": {
                "defaults": {
                    "model": "openai/gpt-5.6-sol",
                    "compaction": {"provider": "lossless-claw"},
                }
            },
        },
    )
    monkeypatch.setattr(doctor_mod, "CONFIG_PATH", cfg_file)
    findings = detect_codex_compaction_overrides(tmp_path, {})
    assert len(findings) == 1
    assert findings[0]["severity"] == "warning"
    assert "manual migration" in findings[0]["message"]
