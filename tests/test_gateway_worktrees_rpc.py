from __future__ import annotations

from pathlib import Path
import subprocess

from src.gateway.worktrees import make_worktrees_handlers, get_worktree_service


def _make_repo(tmp_path: Path) -> Path:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    subprocess.run(["git", "init"], cwd=repo_root, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo_root, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo_root, check=True)
    (repo_root / "README.md").write_text("hello\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repo_root, check=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=repo_root, check=True, capture_output=True, text=True)
    return repo_root


def test_worktrees_rpc_create_list_remove_restore(tmp_path: Path) -> None:
    repo_root = _make_repo(tmp_path)
    svc = get_worktree_service(db_path=tmp_path / "state.sqlite")
    handlers = make_worktrees_handlers(service=svc)

    create = handlers["worktrees.create"]({
        "repo_root": str(repo_root),
        "name": "demo",
        "branch": "feature/demo",
        "owner_kind": "test",
        "owner_id": "u1",
    })
    assert "worktree" in create
    wid = create["worktree"]["id"]

    listed = handlers["worktrees.list"]({})
    assert any(w["id"] == wid for w in listed["worktrees"]) is True

    handlers["worktrees.remove"]({"id": wid})
    assert handlers["worktrees.list"]({})["worktrees"] == []

    restored = handlers["worktrees.restore"]({"id": wid})
    assert restored["worktree"]["id"] == wid
