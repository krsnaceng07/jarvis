from __future__ import annotations

from typing import Any, cast
from pathlib import Path

from src.sessions.session_store import get_default_session_store
from src.logging.secret_redaction_registry import redact_registered_secret_values
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
        created_actor = params.get("created_actor")

        rec = store.get_or_create(
            session_key=session_key, agent_id=agent_id, kind=kind, parent_session_key=parent, thread_id=thread_id, created_actor=created_actor
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
            "created_actor": rec.created_actor,
            "created_at": rec.created_at,
            "updated_at": rec.updated_at,
        }}

    def resolve_handler(params: dict[str, Any]) -> dict[str, Any]:
        target = params.get("target")
        if not target or not isinstance(target, str):
            from .rpc_dispatcher import RPCDispatchError
            raise RPCDispatchError(-32602, "Invalid params: 'target' is required and must be a string")

        # 1. Exact match
        rec = store.get(target)
        if rec:
            return {"session": {"session_key": rec.session_key}}

        # 2. Extract short ID
        # e.g., URL: https://claw.example.com/chat/main/deploy-monitor-6db92d48
        # Shorthand: claw.example.com/main/deploy-monitor-6db92d48
        # Bare: deploy-monitor-6db92d48
        short_id = target.split("/")[-1]

        # 3. Search sessions
        matches = []
        for session in store.list_sessions():
            # Match if the session key ends with the short ID, or contains it.
            if session.session_key.endswith(short_id) or short_id in session.session_key:
                matches.append(session)

        if not matches:
            from .rpc_dispatcher import RPCDispatchError
            raise RPCDispatchError(404, f"Session target not found: {target}")

        if len(matches) > 1:
            # Try to narrow it down to an exact endswith match
            narrowed = [s for s in matches if s.session_key.endswith(short_id)]
            if len(narrowed) == 1:
                matches = narrowed
            else:
                from .rpc_dispatcher import RPCDispatchError
                raise RPCDispatchError(400, f"Ambiguous session target: {target} matched {len(matches)} sessions")

        return {"session": {"session_key": matches[0].session_key}}

    def search_handler(params: dict[str, Any]) -> dict[str, Any]:
        query = params.get("query")
        if not query or not isinstance(query, str):
            from .rpc_dispatcher import RPCDispatchError
            raise RPCDispatchError(-32602, "Invalid params: 'query' is required and must be a string")
        
        limit = params.get("limit", 20)
        if not isinstance(limit, int):
            limit = 20
        # bounds capping
        limit = min(limit, 100)

        results = store.search_sessions(query, limit)
        for res in results:
            # apply redaction to excerpt
            if "excerpt" in res and res["excerpt"]:
                res["excerpt"] = redact_registered_secret_values(res["excerpt"], lambda _: "***")
                # enforce max length on excerpt
                if len(res["excerpt"]) > 500:
                    res["excerpt"] = res["excerpt"][:497] + "..."

        return {"results": results}

    def list_handler(params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        limit = int(params.get("limit", 100))
        offset = int(params.get("offset", 0))
        all_sessions = store.list_sessions()
        sliced = all_sessions[offset : offset + limit] if limit else all_sessions[offset:]
        return {
            "sessions": [
                {
                    "session_key": s.session_key,
                    "sessionId": s.session_key,
                    "agent_id": s.agent_id,
                    "agentId": s.agent_id,
                    "kind": s.kind,
                    "created_at": s.created_at,
                    "updated_at": s.updated_at,
                    "parent_session_key": s.parent_session_key,
                    "thread_id": s.thread_id,
                    "model_ref": s.model_ref,
                    "agent_runtime": s.agent_runtime,
                }
                for s in sliced
            ],
            "total": len(all_sessions),
        }

    def get_handler(params: dict[str, Any]) -> dict[str, Any]:
        params = params or {}
        key = str(params.get("session_key") or params.get("sessionId") or params.get("target") or "")
        if not key:
            from .rpc_dispatcher import RPCDispatchError

            raise RPCDispatchError(-32602, "Invalid params: 'session_key' or 'sessionId' is required")
        rec = store.get(key)
        if rec is None:
            from .rpc_dispatcher import RPCDispatchError

            raise RPCDispatchError(404, f"Session not found: {key}")
        return {
            "session": {
                "session_key": rec.session_key,
                "sessionId": rec.session_key,
                "agent_id": rec.agent_id,
                "agentId": rec.agent_id,
                "kind": rec.kind,
                "created_at": rec.created_at,
                "updated_at": rec.updated_at,
                "entries_count": len(rec.entries),
                "parent_session_key": rec.parent_session_key,
                "thread_id": rec.thread_id,
                "model_ref": rec.model_ref,
                "agent_runtime": rec.agent_runtime,
            }
        }

    def patch_handler(params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        key = str(
            params.get("key")
            or params.get("session_key")
            or params.get("sessionId")
            or params.get("target")
            or ""
        )
        if not key:
            from .rpc_dispatcher import RPCDispatchError

            raise RPCDispatchError(-32602, "Invalid params: 'key' or 'session_key' is required")

        patch_dict = params.get("patch") if isinstance(params.get("patch"), dict) else params
        model = patch_dict.get("model") or patch_dict.get("model_ref")
        agent_runtime = patch_dict.get("agent_runtime") or patch_dict.get("agentRuntime")
        kind = patch_dict.get("kind")
        title = patch_dict.get("title") or patch_dict.get("name")
        created_actor = patch_dict.get("created_actor") or patch_dict.get("createdActor")
        parent_session_key = patch_dict.get("parent_session_key") or patch_dict.get("parentSessionKey")
        thread_id = patch_dict.get("thread_id") or patch_dict.get("threadId")

        rec = store.patch(
            key,
            kind=str(kind) if kind is not None else None,
            model_ref=str(model) if model is not None else None,
            agent_runtime=str(agent_runtime) if agent_runtime is not None else None,
            created_actor=str(created_actor) if created_actor is not None else None,
            parent_session_key=str(parent_session_key) if parent_session_key is not None else None,
            thread_id=str(thread_id) if thread_id is not None else None,
        )
        if rec is None:
            from .rpc_dispatcher import RPCDispatchError

            raise RPCDispatchError(404, f"Session not found: {key}")

        if title:
            store.append_entry(key, {"kind": "session.title", "payload": {"title": str(title)}})
            rec = store.get(key) or rec

        return {
            "ok": True,
            "session": {
                "session_key": rec.session_key,
                "sessionId": rec.session_key,
                "agent_id": rec.agent_id,
                "kind": rec.kind,
                "created_at": rec.created_at,
                "updated_at": rec.updated_at,
                "model_ref": rec.model_ref,
                "agent_runtime": rec.agent_runtime,
                "entries_count": len(rec.entries),
            },
        }

    def delete_handler(params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        key = str(
            params.get("key")
            or params.get("session_key")
            or params.get("sessionId")
            or params.get("target")
            or ""
        )
        if not key:
            from .rpc_dispatcher import RPCDispatchError

            raise RPCDispatchError(-32602, "Invalid params: 'key' or 'session_key' is required")

        deleted = store.delete(key)
        worktree_removed = False
        try:
            worktrees = wt_service.list_worktrees(owner_kind="session", owner_id=key)
            for wt in worktrees:
                wt_service.remove_worktree(wt.id, force=True)
                worktree_removed = True
        except Exception:
            pass

        return {
            "ok": True,
            "key": key,
            "deleted": deleted,
            "worktree_removed": worktree_removed,
        }

    def recover_handler(params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        key = str(
            params.get("key")
            or params.get("session_key")
            or params.get("sessionId")
            or params.get("target")
            or ""
        )
        if not key:
            from .rpc_dispatcher import RPCDispatchError

            raise RPCDispatchError(-32602, "Invalid params: 'key' or 'session_key' is required")

        agent_id = str(params.get("agent_id") or params.get("agentId") or "local")
        rec = store.recover(key, agent_id=agent_id)

        return {
            "ok": True,
            "key": rec.session_key,
            "sessionId": rec.session_key,
            "recovered": True,
            "session": {
                "session_key": rec.session_key,
                "sessionId": rec.session_key,
                "agent_id": rec.agent_id,
                "kind": rec.kind,
                "created_at": rec.created_at,
                "updated_at": rec.updated_at,
                "entries_count": len(rec.entries),
            },
        }

    return {
        "sessions.create": create_handler,
        "session.create": create_handler,
        "sessions.resolve": resolve_handler,
        "session.resolve": resolve_handler,
        "sessions.search": search_handler,
        "session.search": search_handler,
        "sessions.list": list_handler,
        "session.list": list_handler,
        "sessions.get": get_handler,
        "session.get": get_handler,
        "sessions.patch": patch_handler,
        "session.patch": patch_handler,
        "sessions.delete": delete_handler,
        "session.delete": delete_handler,
        "sessions.recover": recover_handler,
        "session.recover": recover_handler,
    }


__all__ = ["make_sessions_handlers"]
