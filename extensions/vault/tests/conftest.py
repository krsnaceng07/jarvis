"""Pytest configuration and fixtures for HashiCorp Vault plugin tests."""

from __future__ import annotations

import importlib.abc
import importlib.util
import sys
from pathlib import Path
from typing import Any
import pytest

# Ensure `extensions.vault` can be imported by tests
PLUGIN_ROOT = Path(__file__).resolve().parent.parent
EXTENSIONS_ROOT = PLUGIN_ROOT.parent

if str(EXTENSIONS_ROOT) not in sys.path:
    sys.path.insert(0, str(EXTENSIONS_ROOT))


class VaultImportFinder(importlib.abc.MetaPathFinder):
    """Bridge import finder for extensions.vault modules."""

    def find_spec(self, fullname: str, path: Any, target: Any = None) -> Any:
        if fullname == "extensions.vault":
            init_py = PLUGIN_ROOT / "__init__.py"
            return importlib.util.spec_from_file_location(
                fullname,
                str(init_py),
                submodule_search_locations=[str(PLUGIN_ROOT)],
            )
        if fullname.startswith("extensions.vault."):
            sub = fullname[len("extensions.vault.") :]
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


if not any(isinstance(f, VaultImportFinder) for f in sys.meta_path):
    sys.meta_path.insert(0, VaultImportFinder())


@pytest.fixture
def sample_token_file(tmp_path: Path) -> Path:
    """Fixture providing a sample token sink file."""
    token_file = tmp_path / "vault-token"
    token_file.write_text("s.mockToken1234567890", encoding="utf-8")
    return token_file


@pytest.fixture
def sample_jwt_file(tmp_path: Path) -> Path:
    """Fixture providing a sample JWT token file."""
    jwt_file = tmp_path / "jwt-token"
    jwt_file.write_text(
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.mockPayload.mockSig", encoding="utf-8"
    )
    return jwt_file
