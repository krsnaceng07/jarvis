"""Pytest configuration for Google Meet extension tests.

Registers `extensions.google_meet` importer into sys.meta_path so all submodules
`extensions.google_meet.*` resolve directly to `extensions/google-meet/*`.
"""

from __future__ import annotations

import importlib.abc
import importlib.machinery
from pathlib import Path
import sys
from typing import Any

_EXT_ROOT = Path(__file__).resolve().parent.parent
_PREFIX = "extensions.google_meet"


class GoogleMeetExtensionFinder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname: str, path: Any = None, target: Any = None) -> Any:
        if fullname == _PREFIX:
            spec = importlib.machinery.ModuleSpec(
                fullname,
                importlib.machinery.SourceFileLoader(fullname, str(_EXT_ROOT / "__init__.py")),
                is_package=True,
                origin=str(_EXT_ROOT / "__init__.py"),
            )
            spec.submodule_search_locations = [str(_EXT_ROOT)]
            return spec

        if fullname.startswith(_PREFIX + "."):
            rel_path = fullname[len(_PREFIX) + 1 :].replace(".", "/")
            # Try as file
            py_file = _EXT_ROOT / f"{rel_path}.py"
            if py_file.is_file():
                return importlib.machinery.ModuleSpec(
                    fullname,
                    importlib.machinery.SourceFileLoader(fullname, str(py_file)),
                    is_package=False,
                    origin=str(py_file),
                )
            # Try as directory/package
            pkg_dir = _EXT_ROOT / rel_path
            pkg_init = pkg_dir / "__init__.py"
            if pkg_dir.is_dir() and pkg_init.is_file():
                spec = importlib.machinery.ModuleSpec(
                    fullname,
                    importlib.machinery.SourceFileLoader(fullname, str(pkg_init)),
                    is_package=True,
                    origin=str(pkg_init),
                )
                spec.submodule_search_locations = [str(pkg_dir)]
                return spec
        return None


if not any(isinstance(finder, GoogleMeetExtensionFinder) for finder in sys.meta_path):
    sys.meta_path.insert(0, GoogleMeetExtensionFinder())
