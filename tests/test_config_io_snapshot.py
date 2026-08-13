import asyncio
import json
import pytest

from src.config.config import (
    get_runtime_config as config_get_runtime_config,
    load_config as config_load_config,
    write_config_file as config_write_config_file,
)
from src.config.io import (
    create_config_io,
    project_config_onto_runtime_source_snapshot,
    read_best_effort_config_snapshot,
    read_config_file_snapshot,
    read_config_file_snapshot_for_runtime_transaction,
    read_config_file_snapshot_for_write,
    read_config_file_snapshot_with_plugin_metadata,
    read_source_config_best_effort,
    read_source_config_snapshot,
    read_source_config_snapshot_for_write,
    recover_config_from_json_root_suffix,
    resolve_shell_env_expected_keys,
)


def test_read_config_file_snapshot_with_plugin_metadata(tmp_path):
    cfg_file = tmp_path / "jarvis.json"
    cfg_file.write_text('{"a": 1}', encoding="utf-8")
    snapshot = read_config_file_snapshot_with_plugin_metadata(config_path=str(cfg_file))
    assert "snapshot" in snapshot
    assert snapshot["snapshot"]["config"] == {"a": 1}
    assert snapshot["pluginMetadataSnapshot"] == {}


def test_read_config_file_snapshot_for_write_returns_snapshot(tmp_path):
    cfg_file = tmp_path / "jarvis.json"
    cfg_file.write_text('{"a": 1}', encoding="utf-8")
    result = read_config_file_snapshot_for_write(config_path=str(cfg_file))
    assert result["config"] == {"a": 1}
    assert result["snapshot"]["config"] == {"a": 1}
    assert result["snapshot"]["hash"] is not None
    assert result["writeOptions"]["expectedConfigPath"] == str(cfg_file)
    assert result["writeOptions"]["ownedConfigPathForWrite"] == str(cfg_file)
    assert callable(result["writeOptions"]["assertConfigPathForWrite"])


def test_read_config_file_snapshot_includes_hash_and_path(tmp_path):
    cfg_file = tmp_path / "jarvis.json"
    cfg_file.write_text('{"a": 1}', encoding="utf-8")
    snapshot = read_config_file_snapshot(config_path=str(cfg_file))
    assert snapshot["path"] == str(cfg_file)
    assert snapshot["exists"] is True
    assert snapshot["hash"] is not None
    assert snapshot["config"] == {"a": 1}


def test_read_config_file_snapshot_for_write_uses_actual_path(tmp_path):
    cfg_file = tmp_path / "jarvis.json"
    cfg_file.write_text('{"a": 1}', encoding="utf-8")
    result = read_config_file_snapshot_for_write(config_path=str(cfg_file))
    assert result["writeOptions"]["expectedConfigPath"] == str(cfg_file)
    assert result["writeOptions"]["ownedConfigPathForWrite"] == str(cfg_file)


def test_read_source_config_snapshot_for_write_returns_snapshot(tmp_path):
    cfg_file = tmp_path / "jarvis.json"
    cfg_file.write_text('{"a": 1}', encoding="utf-8")
    result = read_source_config_snapshot_for_write(config_path=str(cfg_file))
    assert result["config"] == {"a": 1}
    assert result["snapshot"]["config"] == {"a": 1}


def test_read_best_effort_config_snapshot(tmp_path):
    cfg_file = tmp_path / "jarvis.json"
    cfg_file.write_text('{"a": 1}', encoding="utf-8")
    snapshot = read_best_effort_config_snapshot(config_path=str(cfg_file))
    assert snapshot["config"] == {"a": 1}


def test_read_source_config_best_effort(tmp_path):
    cfg_file = tmp_path / "jarvis.json"
    cfg_file.write_text('{"a": 1}', encoding="utf-8")
    result = read_source_config_best_effort(config_path=str(cfg_file))
    assert result == {"a": 1}


def test_read_source_config_snapshot(tmp_path):
    cfg_file = tmp_path / "jarvis.json"
    cfg_file.write_text('{"a": 1}', encoding="utf-8")
    snapshot = read_source_config_snapshot(config_path=str(cfg_file))
    assert snapshot["config"] == {"a": 1}


def test_read_config_file_snapshot_for_runtime_transaction_returns_snapshot(tmp_path):
    cfg_file = tmp_path / "jarvis.json"
    cfg_file.write_text('{"a": 1}', encoding="utf-8")
    snapshot = read_config_file_snapshot_for_runtime_transaction(config_path=str(cfg_file))
    assert snapshot["config"] == {"a": 1}
    assert "writeOptions" not in snapshot


def test_config_facade_delegates_to_io(tmp_path):
    with pytest.raises(NotImplementedError):
        config_load_config()
    with pytest.raises(NotImplementedError):
        config_get_runtime_config()
    cfg_file = tmp_path / "jarvis.json"
    config_write_config_file({"a": 1}, config_path=str(cfg_file))
    assert json.loads(cfg_file.read_text(encoding="utf-8")) == {"a": 1}


def test_project_config_onto_runtime_source_snapshot_delegates(tmp_path):
    runtime_snapshot = {"a": 1}
    source_snapshot = {"a": 1}
    result = project_config_onto_runtime_source_snapshot(
        {"a": 1},
        get_runtime_config_snapshot_fn=lambda: runtime_snapshot,
        get_runtime_config_source_snapshot_fn=lambda: source_snapshot,
        create_merge_patch_fn=lambda runtime, config: config,
    )
    assert result == {"a": 1}


import asyncio


def test_recover_config_from_json_root_suffix_delegates_to_recovery_helper():
    result = asyncio.run(
        recover_config_from_json_root_suffix(
            {"deps": {"json5": {}}, "configPath": "/x"},
            {"exists": True, "valid": False, "raw": "{}"},
        )
    )
    assert result is False


def test_resolve_shell_env_expected_keys_includes_core_and_providers():
    keys = resolve_shell_env_expected_keys(
        {},
        list_known_provider_auth_env_var_names=lambda ctx: ["PROV_KEY"],
        list_known_channel_env_var_names=lambda ctx: ["CHAN_KEY"],
    )
    assert "OPENCLAW_GATEWAY_TOKEN" in keys
    assert "OPENCLAW_GATEWAY_PASSWORD" in keys
    assert "PROV_KEY" in keys
    assert "CHAN_KEY" in keys
