"""Owner-only native Codex thread controls for opted-in homes/supervision."""

from __future__ import annotations

import inspect
from typing import Any, Callable

CodexControlRequest = Callable[[str, dict[str, Any] | None], Any]


def codex_threads_enabled(config: Any, *, is_owner: bool) -> bool:
    """Return whether the native thread tool may be exposed for this run."""
    if not is_owner:
        return False
    app_server = getattr(config, "app_server", None)
    home_scope = getattr(app_server, "home_scope", None)
    supervision = getattr(config, "supervision", None)
    return home_scope == "user" or (
        isinstance(supervision, dict) and supervision.get("enabled") is True
    )


async def execute_codex_threads(
    config: Any,
    params: dict[str, Any],
    request: CodexControlRequest,
    *,
    is_owner: bool,
    session_id: str | None = None,
    attach_fork: Callable[[dict[str, Any]], Any] | None = None,
) -> dict[str, Any]:
    """Execute one guarded native-thread action through the app-server RPC seam."""
    if not codex_threads_enabled(config, is_owner=is_owner):
        raise PermissionError("native Codex thread access is disabled for this run")
    action = _required_string(params, "action")
    supervision = getattr(config, "supervision", None)
    supervision_enabled = isinstance(supervision, dict) and supervision.get("enabled") is True
    raw_allowed = not supervision_enabled or supervision.get("allowRawTranscripts") is True
    mutation = action in {"fork", "rename", "archive", "unarchive"}
    if mutation and supervision_enabled and supervision.get("allowWriteControls") is not True:
        raise PermissionError("native Codex thread mutations are disabled by supervision policy")

    if action == "list":
        search = _optional_string(params.get("search"))
        if search and not raw_allowed:
            raise PermissionError("native Codex thread search is disabled by supervision policy")
        response = await _call(
            request,
            "thread/list",
            {
                "archived": bool(params.get("archived", False)),
                "limit": _bounded_limit(params.get("limit")),
                "modelProviders": [],
                "sortKey": "recency_at",
                "sortDirection": "desc",
                "sourceKinds": ["user"],
                **(
                    {"cursor": _optional_string(params.get("cursor"))}
                    if params.get("cursor")
                    else {}
                ),
                **({"searchTerm": search} if search else {}),
            },
        )
        return _redact_native_thread_response(response) if not raw_allowed else response

    thread_id = _required_string(params, "thread_id")
    if action == "read":
        include_turns = bool(params.get("include_turns", False))
        if include_turns and not raw_allowed:
            raise PermissionError("raw Codex transcript reads are disabled by supervision policy")
        response = await _call(
            request, "thread/read", {"threadId": thread_id, "includeTurns": include_turns}
        )
        return _redact_native_thread_response(response) if not raw_allowed else response

    if action == "rename":
        name = _required_string(params, "name")
        await _call(request, "thread/name/set", {"threadId": thread_id, "name": name})
        return {"action": action, "threadId": thread_id, "name": name}

    if action == "unarchive":
        response = await _call(request, "thread/unarchive", {"threadId": thread_id})
        return _redact_native_thread_response(response) if not raw_allowed else response

    if action == "archive":
        if params.get("confirm") is not True:
            raise ValueError("confirm=true is required to archive a native Codex thread")
        if not session_id:
            raise ValueError("a session identity is required to archive a native Codex thread")
        current = await _read_idle_thread(request, thread_id)
        await _call(request, "thread/archive", {"threadId": thread_id})
        return {"action": action, "threadId": thread_id, "status": current["status"]}

    if action == "fork":
        attach = bool(params.get("attach", True))
        if attach and supervision_enabled:
            raise PermissionError("supervised Codex forks must stay detached; set attach=false")
        if attach:
            if attach_fork is None:
                raise RuntimeError("an attach_fork callback is required for attached Codex forks")
            await _read_idle_thread(request, thread_id)
        response = await _call(
            request,
            "thread/fork",
            {"threadId": thread_id, "threadSource": "user", "excludeTurns": True},
        )
        fork_thread = response.get("thread") if isinstance(response, dict) else None
        if not isinstance(fork_thread, dict) or not _optional_string(fork_thread.get("id")):
            raise ValueError("Codex app-server returned an invalid thread/fork response")
        if attach and attach_fork is not None:
            attached = attach_fork(fork_thread)
            if inspect.isawaitable(attached):
                await attached
        result = {
            "action": action,
            "sourceThreadId": thread_id,
            "thread": fork_thread,
            "attached": attach,
        }
        return _redact_native_thread_response(result) if not raw_allowed else result

    raise ValueError(f"unsupported codex_threads action: {action}")


async def _read_idle_thread(request: CodexControlRequest, thread_id: str) -> dict[str, Any]:
    response = await _call(request, "thread/read", {"threadId": thread_id, "includeTurns": False})
    thread = response.get("thread") if isinstance(response, dict) else None
    if not isinstance(thread, dict) or thread.get("id") != thread_id:
        raise ValueError("Codex app-server returned an invalid thread/read response")
    status = thread.get("status")
    status_type = status.get("type") if isinstance(status, dict) else None
    if status_type not in {"idle", "notLoaded"}:
        raise RuntimeError("cannot operate on an active or unverified Codex thread")
    return {"status": status_type}


async def _call(request: CodexControlRequest, method: str, params: dict[str, Any] | None) -> Any:
    result = request(method, params)
    return await result if inspect.isawaitable(result) else result


def _required_string(params: dict[str, Any], key: str) -> str:
    value = _optional_string(params.get(key))
    if not value:
        raise ValueError(f"{key} is required")
    return value


def _optional_string(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value or None


def _bounded_limit(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        return 20
    return min(max(value, 1), 100)


def _redact_native_thread_response(value: Any) -> Any:
    if not isinstance(value, dict):
        return value
    redacted = dict(value)
    if isinstance(redacted.get("thread"), dict):
        thread = dict(redacted["thread"])
        thread.pop("preview", None)
        thread.pop("turns", None)
        redacted["thread"] = thread
    if isinstance(redacted.get("data"), list):
        redacted["data"] = [
            _redact_native_thread_response(item) if isinstance(item, dict) else item
            for item in redacted["data"]
        ]
    return redacted


__all__ = ["codex_threads_enabled", "execute_codex_threads"]
