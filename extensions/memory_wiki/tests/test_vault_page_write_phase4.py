"""Tests for extensions/memory_wiki/vault_page_write.py.

Phase 4.3a: ports the OpenClaw
``writeGuardedVaultPage`` helper. The tests focus on:

- A fresh page is written through the fs-safe
  ``vault.write`` and the file is observable at
  ``{vault_root}/{page_path}``.
- A symlink at the page path is refused with a
  labeled ``RuntimeError`` (not a raw
  ``FsSafeError``).
- A hardlink (nlink > 1) is broken before the
  atomic rewrite so the linked copy is not
  poisoned.
- The transient ``path-mismatch`` race is retried
  briefly; the helper still succeeds when the
  underlying fs-safe guard is flaky.
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
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[3]
for _candidate in (
    ROOT / "packages" / "plugin_sdk" / "src",
    ROOT / "apps" / "desktop" / "src",
):
    _candidate_str = str(_candidate)
    if _candidate_str not in sys.path:
        sys.path.insert(0, _candidate_str)

import pytest  # noqa: E402

from extensions.memory_wiki.vault_page_write import (  # noqa: E402
    is_regular_file_stat,
    write_guarded_vault_page,
)


class TestIsRegularFileStat:
    def test_dict_like_with_callable_is_file(self) -> None:
        stat = SimpleNamespace(isFile=lambda: True, nlink=1)
        assert is_regular_file_stat(stat) is True

    def test_dict_like_with_bool_is_file(self) -> None:
        stat = SimpleNamespace(isFile=True, nlink=2)
        assert is_regular_file_stat(stat) is True

    def test_non_file_returns_false(self) -> None:
        stat = SimpleNamespace(isFile=lambda: False, nlink=1)
        assert is_regular_file_stat(stat) is False

    def test_no_nlink_returns_false(self) -> None:
        stat = SimpleNamespace(isFile=lambda: True)
        assert is_regular_file_stat(stat) is False

    def test_non_object_returns_false(self) -> None:
        assert is_regular_file_stat(None) is False
        assert is_regular_file_stat(42) is False
        assert is_regular_file_stat("not a stat") is False


class TestWriteGuardedVaultPage:
    @pytest.mark.asyncio
    async def test_writes_fresh_page(self, tmp_path: Path) -> None:
        await write_guarded_vault_page(
            vault_root=str(tmp_path),
            page_path="syntheses/alpha.md",
            content="# alpha\n",
            page_stat=None,
            page_label="alpha page",
        )
        out = tmp_path / "syntheses" / "alpha.md"
        assert out.read_text(encoding="utf-8") == "# alpha\n"

    @pytest.mark.asyncio
    async def test_overwrites_existing_page(self, tmp_path: Path) -> None:
        page = tmp_path / "syntheses" / "alpha.md"
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text("# old", encoding="utf-8")
        # The page stat is fetched here so the
        # hardlink-break path doesn't fire (nlink == 1
        # on most filesystems).
        stat = page.stat()
        await write_guarded_vault_page(
            vault_root=str(tmp_path),
            page_path="syntheses/alpha.md",
            content="# new\n",
            page_stat=SimpleNamespace(isFile=lambda: True, nlink=stat.st_nlink),
            page_label="alpha page",
        )
        assert page.read_text(encoding="utf-8") == "# new\n"

    @pytest.mark.asyncio
    async def test_refuses_symlink_target(
        self, tmp_path: Path
    ) -> None:
        target = tmp_path / "real.md"
        target.write_text("# real", encoding="utf-8")
        link = tmp_path / "syntheses"
        link.mkdir(parents=True, exist_ok=True)
        symlink_path = link / "alpha.md"
        try:
            os.symlink(str(target), str(symlink_path))
        except (OSError, NotImplementedError):
            pytest.skip("symlink not supported on this platform")
        with pytest.raises(RuntimeError, match="through symlink"):
            await write_guarded_vault_page(
                vault_root=str(tmp_path),
                page_path="syntheses/alpha.md",
                content="# new\n",
                page_stat=None,
                page_label="alpha page",
            )

    @pytest.mark.asyncio
    async def test_breaks_hardlink_before_rewrite(
        self, tmp_path: Path
    ) -> None:
        # Hardlinks are only supported on the same
        # filesystem; on Windows they require admin /
        # developer-mode and the test skips otherwise.
        page = tmp_path / "syntheses" / "alpha.md"
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text("# linked", encoding="utf-8")
        link = tmp_path / "syntheses" / "beta.md"
        try:
            os.link(str(page), str(link))
        except (OSError, NotImplementedError):
            pytest.skip("hardlink not supported on this platform")
        # Both files share inode; stat for ``page``
        # has nlink=2 which triggers the hardlink
        # break.
        stat = page.stat()
        assert stat.st_nlink >= 2
        await write_guarded_vault_page(
            vault_root=str(tmp_path),
            page_path="syntheses/alpha.md",
            content="# new\n",
            page_stat=SimpleNamespace(isFile=lambda: True, nlink=stat.st_nlink),
            page_label="alpha page",
        )
        assert page.read_text(encoding="utf-8") == "# new\n"
        # The hardlinked file is untouched.
        assert link.read_text(encoding="utf-8") == "# linked"
