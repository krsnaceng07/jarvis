"""jarvis.agents.embedded_agent_runner.session_manager_init — prepare session manager before run.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/session-manager-init.ts``.

Public surface (mirrors the OpenClaw source):

- :func:`prepare_session_manager_for_run` — normalize the
  session file/state so the first user prompt is persisted
  before the first assistant entry, even for pre-created
  session files.

Phase 7.5a — focused minimal port.

The OpenClaw source uses ``fs`` from ``node:fs/promises``,
``StringDecoder`` from ``node:string_decoder``, the
``isRecord`` coercion, the JSONL serializer, and the
``invalidateSessionFileRepairCache`` helper. The Python port
keeps the public surface and delegates the heavy filesystem +
JSON serialization + session-file-repair-cache invalidation
to installable hooks so the host can plug in the real
filesystem + repair layers as they land.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, Optional


#: Session header entry shape. Mirrors ``SessionHeaderEntry``
#: (``session-manager-init.ts:10-15``).
SessionHeaderEntry = Dict[str, Any]


#: Session message entry shape (subtype). Mirrors
#: ``SessionMessageEntry`` (``session-manager-init.ts:16``).
SessionMessageEntry = Dict[str, Any]


#: First-line read chunk size. Mirrors
#: :data:`SESSION_HEADER_READ_CHUNK_BYTES``
#: (``session-manager-init.ts:18``).
SESSION_HEADER_READ_CHUNK_BYTES: int = 4096


#: Async read-first-line hook. The host installs the real
#: ``fs.open`` + ``StringDecoder`` flow when the filesystem
#: layer lands. The default returns ``None``.
_READ_FIRST_SESSION_FILE_LINE: Callable[[str], Awaitable[Optional[str]]] = (
    lambda _path: _default_read_first_line()
)


async def _default_read_first_line() -> Optional[str]:
    return None


def set_read_first_session_file_line_hook(
    hook: Callable[[str], Awaitable[Optional[str]]],
) -> None:
    """Install a custom read-first-session-file-line hook."""
    global _READ_FIRST_SESSION_FILE_LINE
    _READ_FIRST_SESSION_FILE_LINE = hook


#: Sync write-file hook. The host installs the real
#: ``fs.writeFile`` when the filesystem layer lands. The
#: default returns ``None`` (no-op).
_WRITE_FILE: Callable[[str, str, str], Any] = (
    lambda _path, _content, _encoding: None
)


def set_write_file_hook(
    hook: Callable[[str, str, str], Any],
) -> None:
    """Install a custom write-file hook."""
    global _WRITE_FILE
    _WRITE_FILE = hook


#: Async write-jsonl-lines hook. The host installs the real
#: ``writeJsonlLines`` when the jsonl layer lands. The default
#: returns ``None``.
_WRITE_JSONL_LINES: Callable[..., Awaitable[Any]] = (
    lambda *_args, **_kwargs: _default_write_jsonl()
)


async def _default_write_jsonl() -> None:
    return None


def set_write_jsonl_lines_hook(
    hook: Callable[..., Awaitable[Any]],
) -> None:
    """Install a custom write-jsonl-lines hook."""
    global _WRITE_JSONL_LINES
    _WRITE_JSONL_LINES = hook


#: Sync serialize-jsonl-line hook. The host installs the real
#: ``serializeJsonlLine`` when the jsonl layer lands. The
#: default returns the input as ``str(entry)``.
_SERIALIZE_JSONL_LINE: Callable[[Any], str] = lambda entry: str(entry)


def set_serialize_jsonl_line_hook(
    hook: Callable[[Any], str],
) -> None:
    """Install a custom serialize-jsonl-line hook."""
    global _SERIALIZE_JSONL_LINE
    _SERIALIZE_JSONL_LINE = hook


#: Invalidate-session-file-repair-cache hook. The host installs
#: the real :func:`invalidateSessionFileRepairCache`` when the
#: repair layer lands. The default is a no-op.
_INVALIDATE_SESSION_FILE_REPAIR_CACHE: Callable[[str], Any] = (
    lambda _path: None
)


def set_invalidate_session_file_repair_cache_hook(
    hook: Callable[[str], Any],
) -> None:
    """Install a custom invalidate-session-file-repair-cache hook."""
    global _INVALIDATE_SESSION_FILE_REPAIR_CACHE
    _INVALIDATE_SESSION_FILE_REPAIR_CACHE = hook


#: Is-record check. The host installs the real :func:`isRecord``
#: when the record-coerce layer lands. The default is a
#: duck-type check.
_IS_RECORD: Callable[[Any], bool] = (
    lambda value: (
        isinstance(value, dict)
        and not isinstance(value, list)
        and not isinstance(value, tuple)
    )
)


def set_is_record_hook(
    hook: Callable[[Any], bool],
) -> None:
    """Install a custom is-record hook."""
    global _IS_RECORD
    _IS_RECORD = hook


async def _assert_existing_header_is_readable(
    session_file: str,
) -> None:
    """Read the first line of ``session_file`` and verify it parses.

    Mirrors :func:`assertExistingHeaderIsReadable``
    (``session-manager-init.ts:73-90``).
    """
    import json

    first_line = await _READ_FIRST_SESSION_FILE_LINE(session_file)
    if not first_line:
        return
    try:
        parsed = json.loads(first_line)
    except (TypeError, ValueError) as err:
        raise RuntimeError(
            f"Refusing to reset session transcript with unreadable header: {session_file}"
        ) from err
    if not _IS_RECORD(parsed) or parsed.get("type") != "session":
        raise RuntimeError(
            f"Refusing to reset session transcript with invalid header: {session_file}"
        )


async def prepare_session_manager_for_run(
    *,
    session_manager: Any,
    session_file: str,
    had_session_file: bool,
    session_id: str,
    cwd: str,
) -> None:
    """Normalize the session file/state so the first user prompt persists.

    Mirrors :func:`prepareSessionManagerForRun``
    (``session-manager-init.ts:102-198``).
    """
    sm = session_manager
    file_entries = sm.fileEntries or []
    header = next(
        (e for e in file_entries if isinstance(e, dict) and e.get("type") == "session"),
        None,
    )
    has_assistant = any(
        isinstance(e, dict)
        and e.get("type") == "message"
        and isinstance(e.get("message"), dict)
        and e["message"].get("role") == "assistant"
        for e in file_entries
    )
    if not had_session_file and header is not None:
        header["id"] = session_id
        header["cwd"] = cwd
        sm.sessionId = session_id
        sm.cwd = cwd
        return
    if had_session_file and header is not None and not has_assistant:
        preserves_forked_branch = isinstance(header.get("parentSession"), str) and bool(
            header["parentSession"]
        )
        if sm.wasRecoveredFromCorruptHeader and sm.wasRecoveredFromCorruptHeader() or preserves_forked_branch:
            header["id"] = session_id
            header["cwd"] = cwd
            sm.sessionId = session_id
            sm.cwd = cwd
            lines = sm.getSerializedFileLinesForRewrite() or [
                _SERIALIZE_JSONL_LINE(e) for e in file_entries
            ]
            await _WRITE_JSONL_LINES(session_file, lines, {"mode": 0o600})
            sm.flushed = True
            if sm.syncSnapshotAfterHeaderRewrite:
                sm.syncSnapshotAfterHeaderRewrite("")
            return
        await _assert_existing_header_is_readable(session_file)
        _WRITE_FILE(session_file, "", "utf-8")
        _INVALIDATE_SESSION_FILE_REPAIR_CACHE(session_file)
        header["id"] = session_id
        header["cwd"] = cwd
        sm.sessionId = session_id
        sm.cwd = cwd
        sm.fileEntries = [header]
        if sm.clearPreservedOpaqueFileEntries:
            sm.clearPreservedOpaqueFileEntries()
        if sm.byId is not None and hasattr(sm.byId, "clear"):
            sm.byId.clear()
        if sm.labelsById is not None and hasattr(sm.labelsById, "clear"):
            sm.labelsById.clear()
        if sm.labelTimestampsById is not None and hasattr(
            sm.labelTimestampsById, "clear"
        ):
            sm.labelTimestampsById.clear()
        sm.leafId = None
        sm.flushed = False
        return
    if had_session_file and header is not None:
        header_changed = header.get("id") != session_id or header.get("cwd") != cwd
        header["id"] = session_id
        header["cwd"] = cwd
        sm.sessionId = session_id
        sm.cwd = cwd
        if not header_changed:
            sm.flushed = True
            return
        lines = sm.getSerializedFileLinesForRewrite() or [
            _SERIALIZE_JSONL_LINE(e) for e in file_entries
        ]
        await _WRITE_JSONL_LINES(session_file, lines, {"mode": 0o600})
        sm.flushed = True
        if sm.syncSnapshotAfterHeaderRewrite:
            sm.syncSnapshotAfterHeaderRewrite("")


__all__ = [
    "SESSION_HEADER_READ_CHUNK_BYTES",
    "SessionHeaderEntry",
    "SessionMessageEntry",
    "prepare_session_manager_for_run",
    "set_invalidate_session_file_repair_cache_hook",
    "set_is_record_hook",
    "set_read_first_session_file_line_hook",
    "set_serialize_jsonl_line_hook",
    "set_write_file_hook",
    "set_write_jsonl_lines_hook",
]
