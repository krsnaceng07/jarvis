"""Pytest configuration and fixtures for Fish Audio Speech plugin tests."""

from __future__ import annotations

import importlib.abc
import importlib.util
from pathlib import Path
import sys
from typing import Any
import pytest

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
EXTENSIONS_ROOT = PLUGIN_ROOT.parent

if str(EXTENSIONS_ROOT) not in sys.path:
    sys.path.insert(0, str(EXTENSIONS_ROOT))


class FishAudioSpeechImportFinder(importlib.abc.MetaPathFinder):
    """Bridge import finder for extensions.fish_audio_speech modules."""

    def find_spec(self, fullname: str, path: Any, target: Any = None) -> Any:
        if fullname == "extensions.fish_audio_speech":
            init_py = PLUGIN_ROOT / "__init__.py"
            return importlib.util.spec_from_file_location(
                fullname,
                str(init_py),
                submodule_search_locations=[str(PLUGIN_ROOT), str(PLUGIN_ROOT / "src")],
            )
        if fullname.startswith("extensions.fish_audio_speech."):
            sub = fullname[len("extensions.fish_audio_speech.") :]
            if sub.startswith("src."):
                sub = sub[4:]
            if (PLUGIN_ROOT / "src" / f"{sub}.py").exists():
                return importlib.util.spec_from_file_location(
                    fullname,
                    str(PLUGIN_ROOT / "src" / f"{sub}.py"),
                )
            if (PLUGIN_ROOT / f"{sub}.py").exists():
                return importlib.util.spec_from_file_location(
                    fullname,
                    str(PLUGIN_ROOT / f"{sub}.py"),
                )
            if (PLUGIN_ROOT / "src" / sub / "__init__.py").exists():
                return importlib.util.spec_from_file_location(
                    fullname,
                    str(PLUGIN_ROOT / "src" / sub / "__init__.py"),
                    submodule_search_locations=[str(PLUGIN_ROOT / "src" / sub)],
                )
        return None


if not any(isinstance(f, FishAudioSpeechImportFinder) for f in sys.meta_path):
    sys.meta_path.insert(0, FishAudioSpeechImportFinder())


@pytest.fixture
def sample_fish_config() -> dict[str, dict[str, dict[str, str | float]]]:
    fish_audio: dict[str, str | float] = {
        "apiKey": "test-key-123",
        "model": "s2.1-pro",
        "latency": "low",
        "speed": 1.2,
    }
    providers: dict[str, dict[str, str | float]] = {
        "fish-audio": fish_audio,
    }
    config: dict[str, dict[str, dict[str, str | float]]] = {
        "providers": providers,
    }
    return config

