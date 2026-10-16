"""Pytest configuration and fixtures for Diffs Language Pack plugin tests."""

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


class DiffsLangPackImportFinder(importlib.abc.MetaPathFinder):
    """Bridge import finder for extensions.diffs_language_pack modules."""

    def find_spec(self, fullname: str, path: Any, target: Any = None) -> Any:
        if fullname == "extensions.diffs_language_pack":
            init_py = PLUGIN_ROOT / "__init__.py"
            return importlib.util.spec_from_file_location(
                fullname,
                str(init_py),
                submodule_search_locations=[str(PLUGIN_ROOT)],
            )
        if fullname.startswith("extensions.diffs_language_pack."):
            sub = fullname[len("extensions.diffs_language_pack.") :]
            if (PLUGIN_ROOT / f"{sub}.py").exists():
                return importlib.util.spec_from_file_location(
                    fullname,
                    str(PLUGIN_ROOT / f"{sub}.py"),
                )
        return None


if not any(isinstance(f, DiffsLangPackImportFinder) for f in sys.meta_path):
    sys.meta_path.insert(0, DiffsLangPackImportFinder())
