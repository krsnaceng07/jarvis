from __future__ import annotations

from pathlib import Path
import subprocess

from src.agents.worktrees.service import ManagedWorktreeService


def _make_repo_with_ignored_and_untracked(tmp_path: Path) -> Path:
    repo_root = tmp_path / "repo-provision"
    repo_root.mkdir()
    subprocess.run(["git", "init"], cwd=repo_root, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo_root, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo_root, check=True)
    (repo_root / "README.md").write_text("hello\n", encoding="utf-8")
    (repo_root / ".gitignore").write_text("ignored.log\n", encoding="utf-8")
    (repo_root / "notes.txt").write_text("note123\n", encoding="utf-8")
    (repo_root / "ignored.log").write_text("secret\n", encoding="utf-8")
    (repo_root / ".worktreeinclude").write_text("notes.txt\nignored.log\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md", ".gitignore"], cwd=repo_root, check=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=repo_root, check=True, capture_output=True, text=True)
    return repo_root


def test_provisioning(tmp_path: Path) -> None:
    repo = _make_repo_with_ignored_and_untracked(tmp_path)
    svc = ManagedWorktreeService(db_path=tmp_path / "state-prov.sqlite")
    rec = svc.create_worktree(repo_root=repo, name="prov1", branch="demo", owner_kind="test", owner_id="u1")
    # ensure provisioned files were copied into the worktree
    wp = rec.path
    assert (wp / "notes.txt").exists()
    assert (wp / "ignored.log").exists()
    assert "notes.txt" in rec.provisioned_paths
    assert "ignored.log" in rec.provisioned_paths
