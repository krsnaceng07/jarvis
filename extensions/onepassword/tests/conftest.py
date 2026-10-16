"""Pytest configuration and fixtures for 1Password plugin tests."""

from __future__ import annotations

import importlib.abc
import importlib.util
import sys
from pathlib import Path
from typing import Any
import pytest

# Ensure `extensions.onepassword` can be imported by tests
PLUGIN_ROOT = Path(__file__).resolve().parent.parent
EXTENSIONS_ROOT = PLUGIN_ROOT.parent

if str(EXTENSIONS_ROOT) not in sys.path:
    sys.path.insert(0, str(EXTENSIONS_ROOT))


class OnepasswordImportFinder(importlib.abc.MetaPathFinder):
    """Bridge import finder for extensions.onepassword modules."""

    def find_spec(self, fullname: str, path: Any, target: Any = None) -> Any:
        if fullname == "extensions.onepassword":
            init_py = PLUGIN_ROOT / "__init__.py"
            return importlib.util.spec_from_file_location(
                fullname,
                str(init_py),
                submodule_search_locations=[str(PLUGIN_ROOT)],
            )
        if fullname.startswith("extensions.onepassword."):
            sub = fullname[len("extensions.onepassword.") :]
            # Look in src/ or root
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
        return None


if not any(isinstance(f, OnepasswordImportFinder) for f in sys.meta_path):
    sys.meta_path.insert(0, OnepasswordImportFinder())


@pytest.fixture
def mock_state_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Fixture providing an isolated state directory with service account token."""
    state_dir = tmp_path / "mock_state"
    creds_dir = state_dir / "credentials" / "onepassword"
    creds_dir.mkdir(parents=True, exist_ok=True)
    token_file = creds_dir / "service-account-token"
    token_file.write_text("ops_test_token_1234567890", encoding="utf-8")

    monkeypatch.setenv("OPENCLAW_STATE_DIR", str(state_dir))
    monkeypatch.setenv("JARVIS_STATE_DIR", str(state_dir))
    return state_dir
