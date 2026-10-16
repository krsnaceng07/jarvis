from __future__ import annotations

from pathlib import Path
import subprocess

from src.gateway.worktrees import make_worktrees_handlers, get_worktree_service


def _make_repo(tmp_path: Path) -> Path:
    repo_root = tmp_path / "repo-gc"
    repo_root.mkdir()
    subprocess.run(["git", "init"], cwd=repo_root, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo_root, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo_root, check=True)
    (repo_root / "README.md").write_text("hello\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repo_root, check=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=repo_root, check=True, capture_output=True, text=True)
    return repo_root


def test_gc_removes_old_removed_worktrees(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    svc = get_worktree_service(db_path=tmp_path / "state-gc.sqlite")
    handlers = make_worktrees_handlers(service=svc)

    created = handlers["worktrees.create"]({"repo_root": str(repo), "name": "gctest", "branch": "main", "owner_kind": "test", "owner_id": "u1"})
    wid = created["worktree"]["id"]
    # remove it
    handlers["worktrees.remove"]({"id": wid})
    # make removed_at stale by updating DB directly
    import sqlite3
    conn = sqlite3.connect(str(tmp_path / "state-gc.sqlite"))
    cursor = conn.cursor()
    # set removed_at to a timestamp far in the past
    cursor.execute("UPDATE worktrees SET removed_at = ? WHERE id = ?", (1, wid))
    conn.commit()
    conn.close()

    res = handlers["worktrees.gc"]({"older_than_days": 0})
    assert res["ok"] is True
    assert wid in res["removed"]
    # ensure it's no longer listed
    listed = handlers["worktrees.list"]({})
    assert all(w["id"] != wid for w in listed["worktrees"]) is True
