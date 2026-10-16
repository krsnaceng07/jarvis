from __future__ import annotations

from pathlib import Path
import subprocess

from src.agents.worktrees.service import ManagedWorktreeService


def _make_repo(tmp_path: Path) -> Path:
    repo_root = tmp_path / "repo-hook"
    repo_root.mkdir()
    subprocess.run(["git", "init"], cwd=repo_root, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo_root, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo_root, check=True)
    (repo_root / "README.md").write_text("hello\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repo_root, check=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=repo_root, check=True, capture_output=True, text=True)
    return repo_root


def test_setup_hook_runs(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    oc_dir = repo / ".openclaw"
    oc_dir.mkdir()
    script = oc_dir / "worktree-setup.sh"
    script.write_text("#!/usr/bin/env python3\nimport sys, pathlib\n(p:=pathlib.Path('.')/ 'HOOK_OK').write_text('ok')\n", encoding="utf-8")
    svc = ManagedWorktreeService(db_path=tmp_path / "state-hook.sqlite")
    rec = svc.create_worktree(repo_root=repo, name="hook1", branch="main", owner_kind="test", owner_id="u1")
    assert (rec.path / "HOOK_OK").exists()


def test_setup_hook_failure_cleans_up(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    oc_dir = repo / ".openclaw"
    oc_dir.mkdir()
    script = oc_dir / "worktree-setup.sh"
    script.write_text("#!/usr/bin/env python3\nimport sys\nsys.exit(2)\n", encoding="utf-8")
    svc = ManagedWorktreeService(db_path=tmp_path / "state-hook2.sqlite")
    try:
        svc.create_worktree(repo_root=repo, name="hook2", branch="main", owner_kind="test", owner_id="u1")
        assert False, "expected failure"
    except RuntimeError:
        # ensure no active worktrees remain
        assert svc.list_worktrees() == []
