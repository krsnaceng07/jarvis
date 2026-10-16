"""Codex supervision tools for owner-only session monitoring.

OpenClaw parity: mirrors `extensions/codex/src/supervision-tools.ts`.

These tools expose bounded, paginated read access to Codex sessions across
the gateway and opted-in paired nodes. Write controls (interrupt, steer) and
raw-transcript access are gated behind `supervision.allowWriteControls` and
`supervision.allowRawTranscripts` respectively.

Only registered when `supervision.enabled == True` in the plugin config and
the calling context establishes `sender_is_owner`.
"""

from __future__ import annotations

from typing import Any, Callable, Coroutine

# ---------------------------------------------------------------------------
# Compat tool name set -- mirrors `CODEX_SUPERVISION_COMPAT_TOOL_NAMES`
# ---------------------------------------------------------------------------

CODEX_SUPERVISION_COMPAT_TOOL_NAMES: frozenset[str] = frozenset(
    {
        "codex_endpoint_probe",
        "codex_sessions_list",
        "codex_session_read",
        "codex_session_send",
        "codex_session_interrupt",
    }
)

_DEFAULT_MAX_STORED_SESSIONS = 200
_PAGE_LIMIT = 100
_MAX_COMPAT_CURSOR_LENGTH = 4096
_MAX_COMPAT_THREAD_ID_LENGTH = 4096

_ALL_CODEX_THREAD_SOURCE_KINDS: tuple[str, ...] = (
    "cli",
    "vscode",
    "exec",
    "appServer",
    "subAgent",
    "subAgentReview",
    "subAgentCompact",
    "subAgentThreadSpawn",
    "subAgentOther",
    "unknown",
)

_SupervisionRequestPolicy = str  # "enabled" | "raw-transcripts" | "write-controls"


class CodexSupervisionPolicyError(PermissionError):
    """Raised when a supervision policy gate blocks the requested operation."""


def _supervision_config(get_plugin_config: Callable[[], Any]) -> dict[str, Any]:
    raw = get_plugin_config()
    sup = None
    if hasattr(raw, "supervision"):
        sup = raw.supervision
    elif isinstance(raw, dict):
        sup = raw.get("supervision")
    return sup if isinstance(sup, dict) else {}


def _check_policy(
    supervision: dict[str, Any],
    *,
    policy: _SupervisionRequestPolicy,
) -> None:
    if not supervision.get("enabled"):
        raise CodexSupervisionPolicyError("Codex supervision is not enabled")
    if policy == "raw-transcripts" and supervision.get("allowRawTranscripts") is not True:
        raise CodexSupervisionPolicyError(
            "supervision.allowRawTranscripts must be true to access raw transcripts"
        )
    if policy == "write-controls" and supervision.get("allowWriteControls") is not True:
        raise CodexSupervisionPolicyError(
            "supervision.allowWriteControls must be true to use write controls"
        )


EndpointRequest = Callable[[str, "dict[str, Any] | None"], "Coroutine[Any, Any, Any]"]


async def _probe_endpoint(request: EndpointRequest, supervision: dict[str, Any]) -> dict[str, Any]:
    _check_policy(supervision, policy="enabled")
    try:
        result = await request("version", None)
        return {"ok": True, "detail": result}
    except Exception as exc:
        return {"ok": False, "detail": str(exc)}


async def _sessions_list(
    request: EndpointRequest,
    supervision: dict[str, Any],
    params: dict[str, Any],
) -> dict[str, Any]:
    _check_policy(supervision, policy="enabled")
    max_stored = min(
        int(params.get("max_stored_sessions", _DEFAULT_MAX_STORED_SESSIONS)),
        _DEFAULT_MAX_STORED_SESSIONS,
    )
    result = await request(
        "thread/list",
        {
            "archived": False,
            "limit": _PAGE_LIMIT,
            "sourceKinds": list(_ALL_CODEX_THREAD_SOURCE_KINDS),
            "sortKey": "recency_at",
            "sortDirection": "desc",
        },
    )
    sessions: list[dict[str, Any]] = []
    raw_data = result.get("data", []) if isinstance(result, dict) else []
    for row in raw_data:
        if not isinstance(row, dict):
            continue
        thread_id = row.get("threadId") or row.get("id")
        if not isinstance(thread_id, str) or not thread_id.strip():
            continue
        entry: dict[str, Any] = {"threadId": thread_id, "status": row.get("status", "unknown")}
        for key in ("name", "preview", "cwd", "source", "updatedAt", "humanAttached"):
            if key in row:
                entry[key] = row[key]
        sessions.append(entry)
        if len(sessions) >= max_stored:
            break
    return {"sessions": sessions}


async def _session_read(
    request: EndpointRequest,
    supervision: dict[str, Any],
    params: dict[str, Any],
) -> dict[str, Any]:
    include_turns = bool(params.get("include_turns", False))
    _check_policy(supervision, policy="raw-transcripts" if include_turns else "enabled")
    thread_id = params.get("thread_id")
    if not isinstance(thread_id, str) or not thread_id.strip():
        raise ValueError("thread_id is required")
    rpc: dict[str, Any] = {"threadId": thread_id.strip()}
    if include_turns:
        rpc["includeTurns"] = True
    return await request("thread/read", rpc)


async def _session_send(
    request: EndpointRequest,
    supervision: dict[str, Any],
    params: dict[str, Any],
) -> dict[str, Any]:
    _check_policy(supervision, policy="write-controls")
    thread_id = params.get("thread_id")
    text = params.get("text")
    if not isinstance(thread_id, str) or not thread_id.strip():
        raise ValueError("thread_id is required")
    if not isinstance(text, str) or not text.strip():
        raise ValueError("text is required")
    mode = params.get("mode", "auto")
    if mode not in ("auto", "start", "steer"):
        mode = "auto"
    return await request(
        "thread/send",
        {
            "threadId": thread_id.strip(),
            "text": text.strip(),
            "mode": mode,
        },
    )


async def _session_interrupt(
    request: EndpointRequest,
    supervision: dict[str, Any],
    params: dict[str, Any],
) -> dict[str, Any]:
    _check_policy(supervision, policy="write-controls")
    thread_id = params.get("thread_id")
    if not isinstance(thread_id, str) or not thread_id.strip():
        raise ValueError("thread_id is required")
    rpc: dict[str, Any] = {"threadId": thread_id.strip()}
    if params.get("turn_id"):
        rpc["turnId"] = str(params["turn_id"]).strip()
    return await request("thread/interrupt", rpc)


def create_codex_supervision_tools(
    *,
    get_plugin_config: Callable[[], Any],
    get_runtime_config: "Callable[[], Any] | None" = None,
    resolve_runtime_options: "Callable[..., Any] | None" = None,
    sender_is_owner: bool = False,
) -> list[dict[str, Any]]:
    """Return supervision tool descriptors for owner-only injection.

    OpenClaw parity: mirrors `createCodexSupervisionTools`
    (`supervision-tools.ts`). Returns empty list when not owner so
    registration wrapper never leaks tools to non-owner turns.
    """
    if not sender_is_owner:
        return []
    supervision = _supervision_config(get_plugin_config)
    return [
        {
            "name": "codex_endpoint_probe",
            "description": "Probe the Codex supervision endpoint health.",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
            "_handler": lambda req, p: _probe_endpoint(req, supervision),
        },
        {
            "name": "codex_sessions_list",
            "description": (
                "List non-archived Codex sessions from the Gateway and opted-in paired nodes."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "include_stored": {"type": "boolean"},
                    "max_stored_sessions": {"type": "integer", "minimum": 1, "maximum": 1000},
                },
                "additionalProperties": False,
            },
            "_handler": lambda req, p: _sessions_list(req, supervision, p),
        },
        {
            "name": "codex_session_read",
            "description": "Read metadata and optionally turns of a single Codex session.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "thread_id": {"type": "string"},
                    "include_turns": {"type": "boolean"},
                },
                "required": ["thread_id"],
                "additionalProperties": False,
            },
            "_handler": lambda req, p: _session_read(req, supervision, p),
        },
        {
            "name": "codex_session_send",
            "description": "Send a message to an active or idle Codex session. Requires supervision.allowWriteControls.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "thread_id": {"type": "string"},
                    "text": {"type": "string"},
                    "mode": {"type": "string", "enum": ["auto", "start", "steer"]},
                },
                "required": ["thread_id", "text"],
                "additionalProperties": False,
            },
            "_handler": lambda req, p: _session_send(req, supervision, p),
        },
        {
            "name": "codex_session_interrupt",
            "description": "Interrupt the current turn of an active Codex session. Requires supervision.allowWriteControls.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "thread_id": {"type": "string"},
                    "turn_id": {"type": "string"},
                },
                "required": ["thread_id"],
                "additionalProperties": False,
            },
            "_handler": lambda req, p: _session_interrupt(req, supervision, p),
        },
    ]


__all__ = [
    "CODEX_SUPERVISION_COMPAT_TOOL_NAMES",
    "CodexSupervisionPolicyError",
    "create_codex_supervision_tools",
]
