"""Phase 6.13c — footer_data_provider tests.

Verifies the public surface of:

- :func:`find_git_paths` — locate the
  git ``HEAD`` path by walking up
  from ``cwd``.
- :class:`FooterDataProvider` —
  git-branch + extension-status
  data provider.
- :class:`ReadonlyFooterDataProvider` —
  the read-only view for
  extensions.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path


from src.agents.sessions.footer_data_provider import (
    FooterDataProvider,
    ReadonlyFooterDataProvider,
    find_git_paths,
)


# ============================================================================
# find_git_paths
# ============================================================================


class TestFindGitPaths:
    def test_no_git(self, tmp_path: Path) -> None:
        # tmp_path has no .git.
        assert find_git_paths(str(tmp_path)) is None

    def test_regular_repo(self, tmp_path: Path) -> None:
        # Create a fake .git/HEAD.
        (tmp_path / ".git").mkdir()
        (tmp_path / ".git" / "HEAD").write_text(
            "ref: refs/heads/main\n"
        )
        result = find_git_paths(str(tmp_path))
        assert result is not None
        assert result["repoDir"] == str(tmp_path)
        assert result["headPath"].endswith(os.path.join(".git", "HEAD"))
        assert result["commonGitDir"].endswith(".git")

    def test_walks_up(self, tmp_path: Path) -> None:
        (tmp_path / ".git").mkdir()
        (tmp_path / ".git" / "HEAD").write_text(
            "ref: refs/heads/main\n"
        )
        sub = tmp_path / "a" / "b" / "c"
        sub.mkdir(parents=True)
        result = find_git_paths(str(sub))
        assert result is not None
        assert result["repoDir"] == str(tmp_path)

    def test_worktree(self, tmp_path: Path) -> None:
        # .git is a file pointing to a
        # sibling git dir.
        git_dir = tmp_path / "actual-git"
        git_dir.mkdir()
        (git_dir / "HEAD").write_text("ref: refs/heads/main\n")
        (tmp_path / ".git").write_text(
            f"gitdir: {git_dir}\n"
        )
        result = find_git_paths(str(tmp_path))
        assert result is not None
        # commonGitDir is the actual git
        # dir.
        assert "actual-git" in result["commonGitDir"]


# ============================================================================
# FooterDataProvider
# ============================================================================


class TestFooterDataProvider:
    def test_constructor_no_git(self, tmp_path: Path) -> None:
        provider = FooterDataProvider(str(tmp_path))
        # No git → branch is None.
        assert provider.get_git_branch() is None

    def test_constructor_regular_repo(
        self, tmp_path: Path
    ) -> None:
        (tmp_path / ".git").mkdir()
        (tmp_path / ".git" / "HEAD").write_text(
            "ref: refs/heads/main\n"
        )
        provider = FooterDataProvider(str(tmp_path))
        assert provider.get_git_branch() == "main"

    def test_constructor_detached(self, tmp_path: Path) -> None:
        (tmp_path / ".git").mkdir()
        (tmp_path / ".git" / "HEAD").write_text(
            "abcdef1234567890\n"
        )
        provider = FooterDataProvider(str(tmp_path))
        # Detached HEAD → "detached".
        assert provider.get_git_branch() == "detached"

    def test_extension_statuses(self) -> None:
        provider = FooterDataProvider(tmp_path_fix())
        provider.set_extension_status("key1", "value1")
        provider.set_extension_status("key2", "value2")
        statuses = provider.get_extension_statuses()
        assert statuses == {"key1": "value1", "key2": "value2"}

    def test_set_extension_status_remove(self) -> None:
        provider = FooterDataProvider(tmp_path_fix())
        provider.set_extension_status("key1", "value1")
        provider.set_extension_status("key1", None)
        assert provider.get_extension_statuses() == {}

    def test_available_provider_count(self) -> None:
        provider = FooterDataProvider(tmp_path_fix())
        assert provider.get_available_provider_count() == 0
        provider.set_available_provider_count(3)
        assert provider.get_available_provider_count() == 3

    def test_on_branch_change(self) -> None:
        provider = FooterDataProvider(tmp_path_fix())
        calls: list = []
        unsub = provider.on_branch_change(
            lambda: calls.append("change")
        )
        # Manually notify.
        provider._notify_branch_change()
        assert calls == ["change"]
        unsub()
        provider._notify_branch_change()
        assert calls == ["change"]  # no extra

    def test_callback_exception_doesnt_break(
        self,
    ) -> None:
        provider = FooterDataProvider(tmp_path_fix())

        def _bad() -> None:
            raise RuntimeError("oops")

        provider.on_branch_change(_bad)
        # Should not raise.
        provider._notify_branch_change()

    def test_dispose(self) -> None:
        provider = FooterDataProvider(tmp_path_fix())
        provider.set_extension_status("k", "v")
        unsub_calls: list = []

        def _cb() -> None:
            unsub_calls.append("cb")

        unsub = provider.on_branch_change(_cb)
        provider.dispose()
        # After dispose, callbacks
        # cleared + extension statuses
        # cleared.
        assert provider._branch_change_callbacks == set()
        assert provider.get_extension_statuses() == {}
        assert provider._disposed is True

    def test_refresh_no_change(self, tmp_path: Path) -> None:
        (tmp_path / ".git").mkdir()
        (tmp_path / ".git" / "HEAD").write_text(
            "ref: refs/heads/main\n"
        )
        provider = FooterDataProvider(str(tmp_path))
        # First get caches.
        assert provider.get_git_branch() == "main"
        # Refresh — no change.
        changed = provider.refresh()
        assert changed is False
        assert provider.get_git_branch() == "main"

    def test_refresh_changed(self, tmp_path: Path) -> None:
        (tmp_path / ".git").mkdir()
        (tmp_path / ".git" / "HEAD").write_text(
            "ref: refs/heads/main\n"
        )
        provider = FooterDataProvider(str(tmp_path))
        assert provider.get_git_branch() == "main"
        # Switch branch on disk.
        (tmp_path / ".git" / "HEAD").write_text(
            "ref: refs/heads/feature\n"
        )
        calls: list = []
        provider.on_branch_change(lambda: calls.append("c"))
        changed = provider.refresh()
        assert changed is True
        assert provider.get_git_branch() == "feature"
        assert calls == ["c"]

    def test_refresh_after_dispose(self) -> None:
        provider = FooterDataProvider(tmp_path_fix())
        provider.dispose()
        # No-op after dispose.
        assert provider.refresh() is False


# ============================================================================
# ReadonlyFooterDataProvider
# ============================================================================


class TestReadonlyFooterDataProvider:
    def test_delegates_getters(self) -> None:
        provider = FooterDataProvider(tmp_path_fix())
        provider.set_extension_status("k", "v")
        provider.set_available_provider_count(5)
        view = ReadonlyFooterDataProvider(provider)
        assert view.get_extension_statuses() == {"k": "v"}
        assert view.get_available_provider_count() == 5
        assert view.get_git_branch() is None

    def test_no_setters(self) -> None:
        provider = FooterDataProvider(tmp_path_fix())
        view = ReadonlyFooterDataProvider(provider)
        # Read-only view has no
        # setter methods.
        assert not hasattr(view, "set_extension_status")
        assert not hasattr(view, "set_available_provider_count")
        assert not hasattr(view, "dispose")

    def test_branch_change_subscription(self) -> None:
        provider = FooterDataProvider(tmp_path_fix())
        view = ReadonlyFooterDataProvider(provider)
        calls: list = []
        unsub = view.on_branch_change(
            lambda: calls.append("c")
        )
        provider._notify_branch_change()
        assert calls == ["c"]
        unsub()
        provider._notify_branch_change()
        assert calls == ["c"]


# ============================================================================
# Helpers
# ============================================================================


# Sentinel: pytest's tmp_path fixture
# is per-test; we just need a real
# directory for the no-git tests.
def tmp_path_fix() -> str:  # type: ignore[no-redef]
    return tempfile.mkdtemp()
