from __future__ import annotations

import json
from pathlib import Path
from src.sessions.model_registry import (
    populate_from_config,
    resolve_model,
    get_credentials_for_model,
)
from src.sessions.auth_storage import AuthStorage
from src.sessions.model_registry import get_auth_storage


def test_populate_from_config_with_models(tmp_path: Path) -> None:
    cfg = {
        "models": [
            {
                "id": "claude-haiku-4.5",
                "name": "claude-haiku-4.5",
                "provider": "anthropic",
                "params": {"temperature": 0.2},
                "contextWindow": 4096,
                "authProfile": "anthropic_key",
                "costPer1k": 0.12,
            }
        ]
    }
    cfg_path = tmp_path / "jarvis.json"
    cfg_path.write_text(json.dumps(cfg), encoding="utf-8")

    # Create a minimal api_keys file to simulate auth storage (not required by populate)
    api = {"anthropic_key": {"api_key": "sk-test-123"}}
    api_path = tmp_path / "api_keys.json"
    api_path.write_text(json.dumps(api), encoding="utf-8")

    # Populate from the temp config
    populate_from_config(config_path=cfg_path)

    # The model should be registered
    m = resolve_model("claude-haiku-4.5")
    assert m is not None
    assert m.provider == "anthropic"
    assert m.params.get("temperature") == 0.2
    assert m.context_window == 4096
    assert m.auth_profile == "anthropic_key"
    assert m.cost_per_1k == 0.12


def test_populate_loads_auth_storage(tmp_path: Path) -> None:
    cfg = {"model": "gemini-2.0-flash", "providers": {"default": "gemini"}}
    cfg_path = tmp_path / "jarvis.json"
    cfg_path.write_text(json.dumps(cfg), encoding="utf-8")

    api = {"gemini": {"api_key": "AQ.test"}}
    api_path = tmp_path / "api_keys.json"
    api_path.write_text(json.dumps(api), encoding="utf-8")

    # populate_from_config should load the api_keys.json into module auth storage
    populate_from_config(config_path=cfg_path)
    auth = get_auth_storage()
    assert auth is not None
    assert auth.get("gemini") == {"api_key": "AQ.test"}


def test_auth_storage_normalizes_flat_keys(tmp_path: Path) -> None:
    api = {
        "gemini_api_key": "AQ.flat",
        "openrouter_api_key": "sk-or-flat",
        "extra_service": {"token": "x"},
    }
    api_path = tmp_path / "api_keys.json"
    api_path.write_text(json.dumps(api), encoding="utf-8")

    store = AuthStorage.load_from_file(api_path)
    # gemini_api_key should be normalized to gemini:{api_key:...}
    assert store.get("gemini") == {"api_key": "AQ.flat"}
    # openrouter_api_key preserved as primitive mapping
    assert store.get("openrouter") == "sk-or-flat"
    # extra_service preserved
    assert store.get("extra_service") == {"token": "x"}


def test_get_credentials_precedence(tmp_path: Path, monkeypatch) -> None:
    # Prepare api_keys.json with a provider entry
    api = {"gemini": {"api_key": "AQ.fromfile"}}
    api_path = tmp_path / "api_keys.json"
    api_path.write_text(json.dumps(api), encoding="utf-8")

    store = AuthStorage.load_from_file(api_path)
    # Without env var, provider lookup returns dict
    assert store.get_credentials("gemini") == {"api_key": "AQ.fromfile"}

    # Env var should override
    monkeypatch.setenv("GEMINI_API_KEY", "AQ.env")
    assert store.get_credentials("gemini") == "AQ.env"


def test_get_credentials_for_model(tmp_path: Path, monkeypatch) -> None:
    # Create config with a model referencing an authProfile
    cfg = {
        "models": [
            {
                "id": "m1",
                "name": "m1",
                "provider": "gemini",
                "authProfile": "my_gemini",
            }
        ]
    }
    cfg_path = tmp_path / "jarvis.json"
    cfg_path.write_text(json.dumps(cfg), encoding="utf-8")

    api = {"my_gemini": {"api_key": "AQ.profile"}}
    api_path = tmp_path / "api_keys.json"
    api_path.write_text(json.dumps(api), encoding="utf-8")

    populate_from_config(config_path=cfg_path)
    cred = get_credentials_for_model("m1")
    assert cred == {"api_key": "AQ.profile"}


def test_auth_storage_loads_api_keys(tmp_path: Path) -> None:
    api = {"gemini": {"api_key": "AQ.test"}, "openrouter": "sk-xyz"}
    api_path = tmp_path / "api_keys.json"
    api_path.write_text(json.dumps(api), encoding="utf-8")

    store = AuthStorage.load_from_file(api_path)
    assert store.get("gemini") == {"api_key": "AQ.test"}
    assert store.get("openrouter") == "sk-xyz"
    assert store.get("missing") is None
