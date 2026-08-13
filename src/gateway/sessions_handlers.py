from __future__ import annotations

from typing import Any, cast
from pathlib import Path

from src.sessions.session_store import get_default_session_store
from .worktrees import get_worktree_service, ManagedWorktreeService


def _normalize_worktree_options(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    normalized: dict[str, Any] = {}
    for key, value in cast(dict[Any, Any], raw).items():
        normalized[str(key)] = value
    return normalized


def make_sessions_handlers(service: ManagedWorktreeService | None = None) -> dict[str, Any]:
    store = get_default_session_store()
    wt_service = service or get_worktree_service()

    def create_handler(params: dict[str, Any]) -> dict[str, Any]:
        # Expected params: session_key (optional), agent_id, kind, worktree (optional dict)
        session_key = params.get("session_key") or None
        if session_key is None:
            # allow store to generate a new session id
            import uuid

            session_key = str(uuid.uuid4())
        agent_id = params.get("agent_id", "local")
        kind = params.get("kind", "direct")
        parent = params.get("parent_session_key")
        thread_id = params.get("thread_id")

        rec = store.get_or_create(
            session_key=session_key, agent_id=agent_id, kind=kind, parent_session_key=parent, thread_id=thread_id
        )

        # If a worktree was requested, create it and append an entry.
        wt_opts = _normalize_worktree_options(params.get("worktree"))
        if wt_opts:
            repo_root_raw: object = wt_opts.get("repo_root", ".")
            if not isinstance(repo_root_raw, (str, Path)):
                raise TypeError("worktree.repo_root must be a string or Path")
            repo_root = Path(repo_root_raw).resolve()
            branch_raw: object = wt_opts.get("branch")
            if branch_raw is None:
                branch = f"session-{rec.session_key[:8]}"
            elif isinstance(branch_raw, str):
                branch = branch_raw
            else:
                raise TypeError("worktree.branch must be a string")
            name_raw: object = wt_opts.get("name")
            if name_raw is None:
                name = branch
            elif isinstance(name_raw, str):
                name = name_raw
            else:
                raise TypeError("worktree.name must be a string")
            rec_wt = wt_service.create_worktree(
                repo_root=repo_root,
                name=name,
                branch=branch,
                owner_kind="session",
                owner_id=rec.session_key,
            )
            store.append_entry(rec.session_key, {"kind": "worktree.created", "payload": {"id": rec_wt.id}})

        return {"session": {
            "session_key": rec.session_key,
            "agent_id": rec.agent_id,
            "kind": rec.kind,
            "created_at": rec.created_at,
            "updated_at": rec.updated_at,
        }}

    return {"sessions.create": create_handler}


__all__ = ["make_sessions_handlers"]
