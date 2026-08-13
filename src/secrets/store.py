"""Secrets store — mirrors OpenClaw ``src/secrets/``.

Manages credentials securely in `~/.jarvis/credentials/`.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

_log = logging.getLogger("jarvis.secrets.store")

_CREDENTIALS_DIR = Path.home() / ".jarvis" / "credentials"
_SECRETS_FILE = _CREDENTIALS_DIR / "secrets.json"


class SecretsStore:
    """Read and write encrypted/stored secret keys."""

    def __init__(self, secrets_file: Path | None = None) -> None:
        self.secrets_file = secrets_file or _SECRETS_FILE
        self.secrets_file.parent.mkdir(parents=True, exist_ok=True)

    def _read_data(self) -> dict[str, str]:
        if not self.secrets_file.exists():
            return {}
        try:
            return json.loads(self.secrets_file.read_text(encoding="utf-8"))
        except Exception as e:
            _log.warning("Failed to read secrets file %s: %s", self.secrets_file, e)
            return {}

    def _write_data(self, data: dict[str, str]) -> None:
        try:
            self.secrets_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception as e:
            _log.error("Failed to write secrets file %s: %s", self.secrets_file, e)

    def get_secret(self, key: str) -> str | None:
        return self._read_data().get(key)

    def set_secret(self, key: str, value: str) -> None:
        data = self._read_data()
        data[key] = value
        self._write_data(data)

    def delete_secret(self, key: str) -> bool:
        data = self._read_data()
        if key in data:
            del data[key]
            self._write_data(data)
            return True
        return False

    def list_keys(self) -> list[str]:
        return sorted(self._read_data().keys())


GLOBAL_SECRETS_STORE = SecretsStore()

__all__ = ["GLOBAL_SECRETS_STORE", "SecretsStore"]
