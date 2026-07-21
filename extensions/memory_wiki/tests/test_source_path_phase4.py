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
        # On Windows + Developer Mode, ``os.symlink``
        # works but pytest's tmp_path cleanup walker
        # chokes on dangling symlinks. Use a
        # dedicated subdir that we own + clean up
        # explicitly so the test's cleanup runs
        # before pytest's tmp_path cleanup.
        work = tmp_path / "work"
        work.mkdir()
        link = work / "missing-link.md"
        try:
            os.symlink(str(work / "does-not-exist.md"), str(link))
        except (OSError, NotImplementedError):
            # Skip on Windows without symlink privilege
            # (e.g. unprivileged CI runners).
            import pytest

            pytest.skip("symlink not supported on this platform")
        try:
            # Should not raise even though the target
            # doesn't exist. On POSIX, the result
            # is the lexically-resolved link path
            # (the realpath can't be resolved since
            # the target is missing). On Windows,
            # the result is the lowercased
            # canonical realpath of the missing
            # target (case-insensitive FS resolves
            # the link's lexical target).
            out = resolve_artifact_key(str(link))
            if sys.platform == "win32":
                expected = os.path.realpath(str(link)).lower()
            else:
                expected = os.path.abspath(str(link))
            assert out == expected
        finally:
            # Explicit cleanup BEFORE pytest's
            # tmp_path walker sees the symlink.
            import contextlib

            with contextlib.suppress(OSError):
                os.unlink(str(link))

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
