from __future__ import annotations

from pathlib import Path
import subprocess

from src.gateway.worktrees import make_worktrees_handlers, get_worktree_service


def _make_repo(tmp_path: Path) -> Path:
    repo_root = tmp_path / "repo-snap"
    repo_root.mkdir()
    subprocess.run(["git", "init"], cwd=repo_root, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo_root, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo_root, check=True)
    (repo_root / "README.md").write_text("hello\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repo_root, check=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=repo_root, check=True, capture_output=True, text=True)
    return repo_root


def test_create_snapshot(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    svc = get_worktree_service(db_path=tmp_path / "state-snap.sqlite")
    handlers = make_worktrees_handlers(service=svc)

    created = handlers["worktrees.create"]({"repo_root": str(repo), "name": "snaptest", "branch": "main", "owner_kind": "test", "owner_id": "u1"})
    wid = created["worktree"]["id"]
    wp = created["worktree"]["path"]
    # add a new file in the worktree
    (Path(wp) / "NEW.txt").write_text("new\n", encoding="utf-8")
    snap = handlers["worktrees.snapshot"]({"id": wid, "message": "snap1"})
    sid = snap["snapshot"]["id"]
    commit = snap["snapshot"]["commit"]
    # verify ref exists
    r = subprocess.run(["git", "-C", str(repo), "rev-parse", "refs/openclaw/snapshots/" + sid], check=True, capture_output=True, text=True)
    assert r.stdout.strip() == commit
    # verify NEW.txt exists in tree
    ls = subprocess.run(["git", "-C", str(repo), "ls-tree", "-r", commit], check=True, capture_output=True, text=True)
    assert any("NEW.txt" in l for l in ls.stdout.splitlines())
