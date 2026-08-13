from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from src.agents.worktrees.service import ManagedWorktreeService


def _make_repo(tmp_path: Path) -> Path:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    subprocess.run(["git", "init"], cwd=repo_root, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo_root, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo_root, check=True)
    (repo_root / "README.md").write_text("hello\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repo_root, check=True)
    subprocess.run(
        ["git", "commit", "-m", "initial"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return repo_root


def test_creates_and_removes_worktree(tmp_path: Path) -> None:
    repo_root = _make_repo(tmp_path)
    service = ManagedWorktreeService(
        db_path=tmp_path / "state.sqlite",
        now=lambda: 1_700_000_000_000,
    )

    worktree = service.create_worktree(
        repo_root=repo_root,
        name="feature",
        branch="feature/demo",
        owner_kind="agent",
        owner_id="demo-agent",
    )

    assert worktree.path.exists()
    assert worktree.branch == "feature/demo"
    assert service.list_worktrees()[0].id == worktree.id

    service.remove_worktree(worktree.id)

    assert not worktree.path.exists()
    assert service.list_worktrees() == []


def test_create_worktree_rejects_invalid_openclaw_name(tmp_path: Path) -> None:
    repo_root = _make_repo(tmp_path)
    service = ManagedWorktreeService(
        db_path=tmp_path / "state.sqlite",
        now=lambda: 1_700_000_000_001,
    )

    with pytest.raises(ValueError, match="name"):
        service.create_worktree(
            repo_root=repo_root,
            name="Feature",
            branch="feature/demo",
            owner_kind="agent",
            owner_id="demo-agent",
        )


def test_restore_worktree_is_public_and_rows_are_released(tmp_path: Path) -> None:
    repo_root = _make_repo(tmp_path)
    service = ManagedWorktreeService(
        db_path=tmp_path / "state.sqlite",
        now=lambda: 1_700_000_000_002,
    )

    worktree = service.create_worktree(
        repo_root=repo_root,
        name="feature",
        branch="feature/demo",
        owner_kind="agent",
        owner_id="demo-agent",
    )
    service.remove_worktree(worktree.id)

    restored = service.restore_worktree(worktree.id)

    assert restored.id == worktree.id
    assert restored.removed_at is None
    assert restored.path.exists()
