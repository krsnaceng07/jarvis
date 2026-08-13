from __future__ import annotations

from pathlib import Path
import subprocess

from src.gateway.sessions_handlers import make_sessions_handlers
from src.gateway.worktrees import get_worktree_service, reset_worktree_service
from src.sessions.session_store import get_default_session_store, reset_default_session_store


def _make_repo(tmp_path: Path) -> Path:
    repo_root = tmp_path / "repo2"
    repo_root.mkdir()
    subprocess.run(["git", "init"], cwd=repo_root, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo_root, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo_root, check=True)
    (repo_root / "README.md").write_text("hello\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repo_root, check=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=repo_root, check=True, capture_output=True, text=True)
    return repo_root


def test_sessions_create_with_worktree(tmp_path: Path) -> None:
    reset_default_session_store()
    reset_worktree_service()
    repo_root = _make_repo(tmp_path)
    svc = get_worktree_service(db_path=tmp_path / "state2.sqlite")
    handlers = make_sessions_handlers(service=svc)

    res = handlers["sessions.create"]({
        "agent_id": "a1",
        "kind": "direct",
        "worktree": {"repo_root": str(repo_root), "name": "sesh-demo"},
    })
    assert "session" in res
    # verify that a worktree record exists
    wts = svc.list_worktrees()
    assert len(wts) == 1
