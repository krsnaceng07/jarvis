"""packages/voice_pipeline/src/jarvis_voice_pipeline/key_rotator.py

Thread-safe circular Gemini API Key Rotator.
Maintains a pool of active API keys and automatically rotates to the next key
upon encountering 429 / RESOURCE_EXHAUSTED / Quota limits or connection boundaries.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path
from typing import Sequence

logger = logging.getLogger("jarvis.key_rotator")


class KeyRotator:
    """Manages circular rotation across a pool of Gemini API keys."""

    def __init__(
        self,
        keys: Sequence[str] | None = None,
        config_path: Path | None = None,
    ) -> None:
        self._lock = threading.Lock()
        self._current_index = 0
        self._keys: list[str] = []

        if keys:
            self._keys = [k.strip() for k in keys if k and k.strip()]
        else:
            self._load_from_config(config_path)

        if not self._keys:
            # Fallback to environment variable
            env_key = os.getenv("GEMINI_API_KEY", "").strip()
            if env_key:
                self._keys = [env_key]

        if not self._keys:
            raise ValueError("No Gemini API keys found in configuration or environment.")

    def _load_from_config(self, config_path: Path | None) -> None:
        if config_path is None:
            base_dir = Path(__file__).resolve().parents[4]
            config_path = base_dir / "config" / "api_keys.json"

        if config_path.exists():
            try:
                data = json.loads(config_path.read_text(encoding="utf-8"))
                # Priority: gemini_api_keys list
                if "gemini_api_keys" in data and isinstance(data["gemini_api_keys"], list):
                    self._keys = [
                        k.strip() for k in data["gemini_api_keys"] if isinstance(k, str) and k.strip()
                    ]
                elif "gemini_api_key" in data and isinstance(data["gemini_api_key"], str):
                    self._keys = [data["gemini_api_key"].strip()]
            except Exception as e:
                logger.warning("Failed to load keys from %s: %s", config_path, e)

    @property
    def pool_size(self) -> int:
        with self._lock:
            return len(self._keys)

    @property
    def current_index(self) -> int:
        with self._lock:
            return self._current_index

    def get_current_key(self) -> str:
        with self._lock:
            if not self._keys:
                raise RuntimeError("API key pool is empty.")
            return self._keys[self._current_index]

    def masked_key(self, index: int | None = None) -> str:
        with self._lock:
            if not self._keys:
                return "<empty>"
            idx = self._current_index if index is None else (index % len(self._keys))
            k = self._keys[idx]
            if len(k) <= 8:
                return "***"
            return f"{k[:4]}...{k[-4:]}"

    def rotate(self, reason: str = "") -> tuple[str, int]:
        """Advance to the next key in the pool cyclically.
        Returns (new_key, new_index).
        """
        with self._lock:
            if not self._keys:
                raise RuntimeError("API key pool is empty.")
            prev_idx = self._current_index
            self._current_index = (self._current_index + 1) % len(self._keys)
            new_key = self._keys[self._current_index]

            logger.info(
                "Gemini API key rotated from #%d [%s] -> #%d [%s]. Reason: %s",
                prev_idx + 1,
                self._mask(self._keys[prev_idx]),
                self._current_index + 1,
                self._mask(new_key),
                reason or "manual/rate-limit",
            )
            return new_key, self._current_index

    @staticmethod
    def _mask(k: str) -> str:
        if len(k) <= 8:
            return "***"
        return f"{k[:4]}...{k[-4:]}"


_DEFAULT_ROTATOR: KeyRotator | None = None
_ROTATOR_LOCK = threading.Lock()


def get_default_key_rotator() -> KeyRotator:
    """Singleton provider for KeyRotator."""
    global _DEFAULT_ROTATOR
    with _ROTATOR_LOCK:
        if _DEFAULT_ROTATOR is None:
            _DEFAULT_ROTATOR = KeyRotator()
        return _DEFAULT_ROTATOR
