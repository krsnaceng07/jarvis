"""Tests for extensions/memory_wiki/source_path_shared.py.

Phase 4.3a: ports the OpenClaw
``resolveArtifactKey`` helper. The tests focus on:

- POSIX: the key is the canonical realpath,
  unaltered.
- POSIX: a dangling symlink falls back to the
  lexically-resolved path (no exception).
- Windows: the key is the canonical realpath
  lowercased (the filesystem is case-insensitive).
"""

# pyright: reportArgumentType=false
# pyright: reportAttributeAccessIssue=false
# pyright: reportCallIssue=false
# pyright: reportGeneralTypeIssues=false
# pyright: reportIndexIssue=false
# pyright: reportOptionalMemberAccess=false
# pyright: reportOptionalSubscript=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
# pyright: reportReturnType=false
# pyright: reportTypedDictNotRequiredAccess=false

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
for _candidate in (
    ROOT / "packages" / "plugin_sdk" / "src",
    ROOT / "apps" / "desktop" / "src",
):
    _candidate_str = str(_candidate)
    if _candidate_str not in sys.path:
        sys.path.insert(0, _candidate_str)

from extensions.memory_wiki.source_path_shared import (  # noqa: E402
    resolve_artifact_key,
)


class TestResolveArtifactKey:
    def test_real_file_returns_canonical_path(self, tmp_path: Path) -> None:
        f = tmp_path / "alpha.md"
        f.write_text("# alpha", encoding="utf-8")
        out = resolve_artifact_key(str(f))
        # The canonical path is the realpath on POSIX
        # and the lowercased realpath on Windows.
        if sys.platform == "win32":
            assert out == os.path.realpath(str(f)).lower()
        else:
            assert out == os.path.realpath(str(f))

    def test_dangling_symlink_falls_back(self, tmp_path: Path) -> None:
        link = tmp_path / "missing-link.md"
        try:
            os.symlink(str(tmp_path / "does-not-exist.md"), str(link))
        except (OSError, NotImplementedError):
            # Skip on Windows without symlink privilege
            # (e.g. unprivileged CI runners).
            import pytest

            pytest.skip("symlink not supported on this platform")
        # Should not raise even though the target
        # doesn't exist.
        out = resolve_artifact_key(str(link))
        assert out == os.path.abspath(str(link))

    def test_relative_input_uses_lexical_abspath(self, tmp_path: Path) -> None:
        # No realpath mutation needed; the function
        # just needs to return the absolute path
        # under POSIX.
        cwd = os.getcwd()
        try:
            os.chdir(str(tmp_path))
            out = resolve_artifact_key("notes/alpha.md")
            assert os.path.isabs(out)
        finally:
            os.chdir(cwd)
