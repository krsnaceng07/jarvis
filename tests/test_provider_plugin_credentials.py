from __future__ import annotations

import json
from pathlib import Path
from src.sessions.model_registry import populate_from_config, get_auth_storage

from extensions.google.plugin import google_provider
from extensions.anthropic.plugin import anthropic_provider


def test_provider_init_attaches_credentials(tmp_path: Path) -> None:
    cfg = {
        "models": [
            {
                "id": "g1",
                "name": "gemini-2.0-flash",
                "provider": "google",
            },
            {
                "id": "a1",
                "name": "claude-sonnet-4-6",
                "provider": "anthropic",
                "authProfile": "anthropic_key",
            },
        ]
    }
    cfg_path = tmp_path / "jarvis.json"
    cfg_path.write_text(json.dumps(cfg), encoding="utf-8")

    api = {"anthropic_key": {"api_key": "sk-test-123"}, "google": {"api_key": "AQ.test"}}
    api_path = tmp_path / "api_keys.json"
    api_path.write_text(json.dumps(api), encoding="utf-8")

    populate_from_config(config_path=cfg_path)

    # The underlying auth storage should contain the expected profiles
    auth = get_auth_storage()
    assert auth is not None
    assert auth.get("anthropic_key") == {"api_key": "sk-test-123"}
    assert auth.get("google") == {"api_key": "AQ.test"}

    # Calling provider.init should not raise (best-effort wiring)
    anthropic_provider.init(None)
    google_provider.init(None)
