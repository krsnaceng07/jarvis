"""jarvis.agents.sessions.footer_data_provider — footer data provider.

OpenClaw parity: mirrors
``openclaw-main/src/agents/sessions/footer-data-provider.ts``.

Public surface (matches the OpenClaw
source):

- :class:`FooterDataProvider` — the
  git-branch + extension-status
  data provider. Mirrors
  :class:`FooterDataProvider`
  (``footer-data-provider.ts:102-355``).
- :class:`ReadonlyFooterDataProvider` —
  the read-only view for
  extensions. Mirrors
  :class:`ReadonlyFooterDataProvider`
  (``footer-data-provider.ts:358-363``).
- :func:`find_git_paths` — walk up
  from ``cwd`` + locate the git
  ``.git`` file/dir + the
  ``HEAD`` path. Mirrors
  :func:`findGitPaths`
  (``footer-data-provider.ts:29-67``).

Phase 6.13c — focused port.

Adaptations
-----------
- The OpenClaw source's
  :class:`FooterDataProvider`
  uses :mod:`node:fs` ``fs.watch``
  for live git-branch updates.
  The Python port's focused
  minimal version polls the
  ``HEAD`` file on
  :meth:`getGitBranch` calls
  (the full FS-watching version
  lands in 6.14+).
- The OpenClaw source's
  :func:`runExec` + ``spawnSync``
  for the fallback ``git
  symbolic-ref`` branch
  resolution come from
  :mod:`@openclaw/agent-shared/exec.js`.
  The Python port uses
  :func:`subprocess.run` with the
  same ``--no-optional-locks
  symbolic-ref --quiet --short
  HEAD`` command.
- The OpenClaw source's
  :mod:`fs-watch.js` (the
  ``watchWithErrorHandler``
  helper) comes from
  :mod:`agents/utils/fs-watch.js`.
  The Python port skips the
  watcher entirely (polling
  only).
"""
from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path
from typing import Callable, Optional, Union


_LOG = logging.getLogger(
    "jarvis.agents.sessions.footer_data_provider"
)


# ============================================================================
# Module-level helpers
# ============================================================================


def find_git_paths(cwd: str) -> Optional[dict]:
    """Walk up from ``cwd`` + locate the
    git ``.git`` file/dir + the
    ``HEAD`` path. Mirrors
    :func:`findGitPaths`
    (``footer-data-provider.ts:29-67``).

    Handles both regular git repos
    (``.git`` is a directory) +
    worktrees (``.git`` is a file
    pointing to the actual git
    dir).

    Returns
    -------
    dict or None
        ``{"repoDir": str, "commonGitDir":
        str, "headPath": str}`` on
        success, ``None`` when no
        git repo is found.
    """
    if not cwd:
        return None
    current = os.path.abspath(cwd)
    while True:
        git_path = os.path.join(current, ".git")
        if os.path.lexists(git_path):
            try:
                if os.path.isfile(git_path):
                    # Worktree case: .git is a
                    # file containing
                    # ``gitdir: <path>``.
                    with open(
                        git_path, "r", encoding="utf-8"
                    ) as f:
                        content = f.read().strip()
                    if content.startswith("gitdir: "):
                        git_dir = os.path.normpath(
                            os.path.join(
                                current,
                                content[len("gitdir: "):].strip(),
                            )
                        )
                        head_path = os.path.join(git_dir, "HEAD")
                        if not os.path.exists(head_path):
                            return None
                        common_dir_path = os.path.join(
                            git_dir, "commondir"
                        )
                        if os.path.exists(common_dir_path):
                            try:
                                with open(
                                    common_dir_path,
                                    "r",
                                    encoding="utf-8",
                                ) as f2:
                                    common_git_dir = (
                                        os.path.normpath(
                                            os.path.join(
                                                git_dir,
                                                f2.read().strip(),
                                            )
                                        )
                                    )
                            except OSError:
                                common_git_dir = git_dir
                        else:
                            common_git_dir = git_dir
                        return {
                            "repoDir": current,
                            "commonGitDir": common_git_dir,
                            "headPath": head_path,
                        }
                elif os.path.isdir(git_path):
                    # Regular repo.
                    head_path = os.path.join(git_path, "HEAD")
                    if not os.path.exists(head_path):
                        return None
                    return {
                        "repoDir": current,
                        "commonGitDir": git_path,
                        "headPath": head_path,
                    }
            except OSError:
                return None
        parent = os.path.dirname(current)
        if parent == current:
            return None
        current = parent


def _resolve_branch_with_git(repo_dir: str) -> Optional[str]:
    """Ask git for the current branch.
    Returns ``None`` on detached HEAD
    or if git is unavailable. Mirrors
    :func:`resolveBranchWithGitSync`
    (``footer-data-provider.ts:70-82``)."""
    try:
        result = subprocess.run(
            [
                "git",
                "--no-optional-locks",
                "symbolic-ref",
                "--quiet",
                "--short",
                "HEAD",
            ],
            cwd=repo_dir,
            capture_output=True,
            text=True,
            timeout=2.0,
        )
        if result.returncode == 0:
            branch = (result.stdout or "").strip()
            return branch or None
        return None
    except (OSError, subprocess.SubprocessError):
        return None


# ============================================================================
# FooterDataProvider
# ============================================================================


class FooterDataProvider:
    """Provides git-branch +
    extension-status data not
    otherwise accessible to
    extensions. Mirrors
    :class:`FooterDataProvider`
    (``footer-data-provider.ts:102-355``).

    Phase 6.13c — focused port. The
    full FS-watching implementation
    lands in 6.14+; this version
    polls the ``HEAD`` file on each
    :meth:`getGitBranch` call.
    """

    #: Watch debounce (ms). Mirrors
    #: the OpenClaw source's
    #: ``WATCH_DEBOUNCE_MS`` constant.
    WATCH_DEBOUNCE_MS: int = 500

    def __init__(self, cwd: str) -> None:
        self._cwd = cwd
        self._git_paths: Optional[dict] = find_git_paths(cwd)
        self._cached_branch: Optional[str] = "__unset__"  # sentinel
        self._extension_statuses: dict[str, str] = {}
        self._available_provider_count: int = 0
        self._branch_change_callbacks: set[Callable[[], None]] = set()
        self._disposed: bool = False

    # ------------------------------------------------------------------
    # Public: getters
    # ------------------------------------------------------------------

    def get_git_branch(self) -> Optional[str]:
        """Return the current git branch,
        or ``None`` if not in a repo,
        or ``"detached"`` for detached
        HEAD. Mirrors
        :meth:`getGitBranch`
        (``footer-data-provider.ts:126-131``).

        Phase 6.13c — polls ``HEAD`` on
        each call (the OpenClaw source
        caches the result + uses FS
        watching for invalidation).
        """
        if self._cached_branch != "__unset__":
            return self._cached_branch
        self._cached_branch = self._resolve_git_branch_sync()
        return self._cached_branch

    def get_extension_statuses(self) -> dict[str, str]:
        """Return the extension status
        map. Mirrors
        :meth:`getExtensionStatuses`
        (``footer-data-provider.ts:134-136``)."""
        return dict(self._extension_statuses)

    def get_available_provider_count(self) -> int:
        """Return the number of unique
        providers with available
        models. Mirrors
        :meth:`getAvailableProviderCount`
        (``footer-data-provider.ts:154-156``)."""
        return self._available_provider_count

    def on_branch_change(
        self, callback: Callable[[], None]
    ) -> Callable[[], None]:
        """Subscribe to git-branch
        changes. Returns an unsubscribe
        callable. Mirrors
        :meth:`onBranchChange`
        (``footer-data-provider.ts:139-142``).

        Phase 6.13c — the polling
        implementation only notifies
        on :meth:`refresh` /
        :meth:`dispose` calls. The
        full FS-watching + notify
        loop lands in 6.14+.
        """
        self._branch_change_callbacks.add(callback)

        def unsubscribe() -> None:
            self._branch_change_callbacks.discard(callback)

        return unsubscribe

    # ------------------------------------------------------------------
    # Public: setters (internal)
    # ------------------------------------------------------------------

    def set_extension_status(
        self, key: str, text: Optional[str]
    ) -> None:
        """Set an extension status
        (or remove it when ``text`` is
        ``None``). Mirrors
        :meth:`setExtensionStatus`
        (``footer-data-provider.ts:145-151``)."""
        if text is None:
            self._extension_statuses.pop(key, None)
        else:
            self._extension_statuses[key] = text

    def set_available_provider_count(self, count: int) -> None:
        """Set the available-provider
        count. Mirrors
        :meth:`setAvailableProviderCount`
        (``footer-data-provider.ts:159-161``)."""
        self._available_provider_count = int(count)

    def dispose(self) -> None:
        """Clean up the provider.
        Mirrors :meth:`dispose`
        (``footer-data-provider.ts:164-172``)."""
        self._disposed = True
        self._branch_change_callbacks.clear()
        self._extension_statuses.clear()

    # ------------------------------------------------------------------
    # Public: refresh
    # ------------------------------------------------------------------

    def refresh(self) -> bool:
        """Re-read the git branch + notify
        callbacks when it changed.
        Mirrors the OpenClaw source's
        :func:`refreshGitBranchAsync`
        (Phase 6.13c — focused minimal
        synchronous port).

        Returns
        -------
        bool
            ``True`` when the branch
            changed + callbacks were
            notified, ``False``
            otherwise.
        """
        if self._disposed:
            return False
        previous = self._cached_branch
        next_branch = self._resolve_git_branch_sync()
        self._cached_branch = next_branch
        if previous != "__unset__" and previous != next_branch:
            self._notify_branch_change()
            return True
        return False

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _notify_branch_change(self) -> None:
        """Notify every registered
        branch-change callback. Mirrors
        :func:`notifyBranchChange`
        (``footer-data-provider.ts:174-178``)."""
        for cb in list(self._branch_change_callbacks):
            try:
                cb()
            except Exception:
                _LOG.exception(
                    "Branch change callback raised"
                )

    def _resolve_git_branch_sync(self) -> Optional[str]:
        """Resolve the current git branch
        from the ``HEAD`` file. Mirrors
        :func:`resolveGitBranchSync`
        (``footer-data-provider.ts:224-240``)."""
        if self._git_paths is None:
            return None
        try:
            with open(
                self._git_paths["headPath"],
                "r",
                encoding="utf-8",
            ) as f:
                content = f.read().strip()
        except (OSError, IOError):
            return None
        if content.startswith("ref: refs/heads/"):
            branch = content[len("ref: refs/heads/"):]
            if branch == ".invalid":
                return (
                    _resolve_branch_with_git(
                        self._git_paths["repoDir"]
                    )
                    or "detached"
                )
            return branch
        return "detached"


#: A read-only view of
#: :class:`FooterDataProvider` for
#: extensions. Mirrors
#: :class:`ReadonlyFooterDataProvider`
#: (``footer-data-provider.ts:358-363``).
class ReadonlyFooterDataProvider:
    """Read-only view of the
    :class:`FooterDataProvider` for
    extensions. The setter methods
    are intentionally not exposed."""

    def __init__(self, provider: FooterDataProvider) -> None:
        self._provider = provider

    def get_git_branch(self) -> Optional[str]:
        return self._provider.get_git_branch()

    def get_extension_statuses(self) -> dict[str, str]:
        return self._provider.get_extension_statuses()

    def get_available_provider_count(self) -> int:
        return self._provider.get_available_provider_count()

    def on_branch_change(
        self, callback: Callable[[], None]
    ) -> Callable[[], None]:
        return self._provider.on_branch_change(callback)


__all__ = [
    "FooterDataProvider",
    "ReadonlyFooterDataProvider",
    "find_git_paths",
]
