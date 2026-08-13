from __future__ import annotations

import uuid
from typing import Any
from pathlib import Path

from src.agents.worktrees.service import ManagedWorktreeService

# Simple singleton for wiring in the gateway startup
_SERVICE: ManagedWorktreeService | None = None


def get_worktree_service(db_path: Path | str = "~/.jarvis/state.sqlite") -> ManagedWorktreeService:
    global _SERVICE
    db_path = str(Path(db_path).expanduser().resolve())
    if _SERVICE is None or _SERVICE._db_path != db_path:
        _SERVICE = ManagedWorktreeService(db_path=db_path)
    return _SERVICE


def reset_worktree_service() -> None:
    global _SERVICE
    _SERVICE = None


def make_worktrees_handlers(service: ManagedWorktreeService | None = None) -> dict[str, Any]:
    svc = service or get_worktree_service()

    def list_handler(params: dict[str, Any]) -> dict[str, Any]:
        out = [r.__dict__ for r in svc.list_worktrees()]
        # convert Path -> str
        for o in out:
            o["path"] = str(o["path"])
        return {"worktrees": out}

    def create_handler(params: dict[str, Any]) -> dict[str, Any]:
        repo_root_raw: object = params.get("repo_root", ".")
        if not isinstance(repo_root_raw, (str, Path)):
            raise TypeError("repo_root must be a string or Path")
        repo_root = Path(repo_root_raw).resolve()

        name_raw: object = params.get("name")
        if not isinstance(name_raw, str):
            raise TypeError("name must be a string")
        name = name_raw

        branch_raw: object = params.get("branch")
        if branch_raw is None:
            branch = f"worktree-{uuid.uuid4().hex[:8]}"
        elif isinstance(branch_raw, str):
            branch = branch_raw
        else:
            raise TypeError("branch must be a string")

        base_ref_raw: object = params.get("base_ref", "HEAD")
        if not isinstance(base_ref_raw, str):
            raise TypeError("base_ref must be a string")
        base_ref = base_ref_raw

        owner_kind_raw: object = params.get("owner_kind", "manual")
        if not isinstance(owner_kind_raw, str):
            raise TypeError("owner_kind must be a string")
        owner_kind = owner_kind_raw

        owner_id_raw: object = params.get("owner_id")
        owner_id = owner_id_raw if isinstance(owner_id_raw, str) else None

        rec = svc.create_worktree(
            repo_root=repo_root,
            name=name,
            branch=branch,
            owner_kind=owner_kind,
            owner_id=owner_id,
            base_ref=base_ref,
        )
        d = dict(rec.__dict__)
        d["path"] = str(d["path"])
        return {"worktree": d}

    def remove_handler(params: dict[str, Any]) -> dict[str, Any]:
        worktree_id_raw = params.get("id")
        if not isinstance(worktree_id_raw, str):
            raise TypeError("id must be a string")
        svc.remove_worktree(worktree_id_raw)
        return {"ok": True}

    def restore_handler(params: dict[str, Any]) -> dict[str, Any]:
        worktree_id_raw = params.get("id")
        if not isinstance(worktree_id_raw, str):
            raise TypeError("id must be a string")
        rec = svc.restore_worktree(worktree_id_raw)
        d = dict(rec.__dict__)
        d["path"] = str(d["path"])
        return {"worktree": d}

    def gc_handler(params: dict[str, Any]) -> dict[str, Any]:
        # params: { "older_than_days": int }
        days_raw = params.get("older_than_days", 7)
        if not isinstance(days_raw, int):
            raise TypeError("older_than_days must be an integer")
        days = days_raw
        ms = days * 24 * 60 * 60 * 1000
        removed = svc.gc_collect(ms)
        return {"ok": True, "removed": removed}

    def snapshot_handler(params: dict[str, Any]) -> dict[str, Any]:
        worktree_id_raw = params.get("id")
        if not isinstance(worktree_id_raw, str):
            raise TypeError("id must be a string")
        message_raw = params.get("message")
        message = message_raw if isinstance(message_raw, str) else None
        snap = svc.create_snapshot(worktree_id_raw, message=message)
        return {"snapshot": snap}

    handlers = {
        "worktrees.list": list_handler,
        "worktrees.create": create_handler,
        "worktrees.remove": remove_handler,
        "worktrees.restore": restore_handler,
        "worktrees.gc": gc_handler,
        "worktrees.snapshot": snapshot_handler,
    }
    return handlers


__all__ = ["get_worktree_service", "make_worktrees_handlers"]
