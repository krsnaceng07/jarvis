"""Pytest configuration and fixtures for Talk Voice plugin tests."""

from __future__ import annotations

import importlib.abc
import importlib.util
from pathlib import Path
import sys
from typing import Any

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
EXTENSIONS_ROOT = PLUGIN_ROOT.parent

if str(EXTENSIONS_ROOT) not in sys.path:
    sys.path.insert(0, str(EXTENSIONS_ROOT))


class TalkVoiceImportFinder(importlib.abc.MetaPathFinder):
    """Bridge import finder for extensions.talk_voice modules."""

    def find_spec(self, fullname: str, path: Any, target: Any = None) -> Any:
        if fullname == "extensions.talk_voice":
            init_py = PLUGIN_ROOT / "__init__.py"
            return importlib.util.spec_from_file_location(
                fullname,
                str(init_py),
                submodule_search_locations=[str(PLUGIN_ROOT), str(PLUGIN_ROOT / "src")],
            )
        if fullname.startswith("extensions.talk_voice."):
            sub = fullname[len("extensions.talk_voice.") :]
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


if not any(isinstance(f, TalkVoiceImportFinder) for f in sys.meta_path):
    sys.meta_path.insert(0, TalkVoiceImportFinder())
