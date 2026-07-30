"""jarvis.agents.sessions.session_manager_list — session discovery.

OpenClaw parity: mirrors
``openclaw-main/src/agents/sessions/session-manager-list.ts``.

Discovers on-disk session files (``.jsonl`` in the
sessions directory) and builds a
:class:`SessionInfo` per file. Bounded concurrency
for the discovery + read.

Parity
======
- ``MAX_CONCURRENT_SESSION_INFO_LOADS = 10``
  (``session-manager-list.ts:19``).
- ``MAX_SESSION_HEADER_BYTES = 64 * 1024``
  (``session-manager-list.ts:18``).
- ``find_most_recent_session(session_dir, cwd?)``
  (``session-manager-list.ts:61-77``) — returns
  the most recently modified ``.jsonl`` file
  whose header matches ``cwd`` (or any cwd when
  ``cwd`` is None).
- ``list_sessions(cwd, session_dir, on_progress?)``
  (``session-manager-list.ts:244-252``) — all
  sessions in ``session_dir`` for ``cwd``.
- ``list_all_sessions(on_progress?)``
  (``session-manager-list.ts:254-296``) — every
  session across all session sub-dirs.

Phase 6.3 — session IO + discovery.

Adaptations
-----------
- The OpenClaw source uses ``pMap`` (the npm
  package) for concurrency control. The Python
  port uses
  :class:`concurrent.futures.ThreadPoolExecutor`
  with the same ``MAX_CONCURRENT_SESSION_INFO_LOADS``
  (10) cap.
- The OpenClaw source uses ``readdirSync`` /
  ``readFileSync`` (synchronous) but the
  ``listSessions`` / ``listAllSessions`` functions
  are ``async``. The Python port keeps the
  ``async`` signature (matches the
  ``SessionListProgress`` callback contract);
  the synchronous file IO is wrapped in a
  thread pool to avoid blocking the event loop.
- The OpenClaw source reads the first line of
  each session file via
  ``readFirstSessionFileLine`` (a 4 KB-chunk
  read loop). The Python port uses
  :func:`_read_first_session_file_line` with the
  same constants.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

from .session_manager_file import get_default_session_dir
from .session_manager_types import (
    FileEntry,
    SessionHeader,
    SessionInfo,
    SessionListProgress,
)


_LOG = logging.getLogger("jarvis.agents.sessions.session_manager_list")

#: 4 KB chunk for the header-read loop. Mirrors
#: ``SESSION_HEADER_READ_CHUNK_BYTES``
#: (``session-manager-list.ts:17``).
_SESSION_HEADER_READ_CHUNK_BYTES = 4096

#: Maximum bytes to read when looking for the
#: header. Mirrors ``MAX_SESSION_HEADER_BYTES``
#: (``session-manager-list.ts:18``). 64 KB is
#: enough for the largest canonical header
#: (~500 bytes) with plenty of headroom.
_MAX_SESSION_HEADER_BYTES = 64 * 1024

#: Concurrency cap for the info-loader pool.
#: Mirrors ``MAX_CONCURRENT_SESSION_INFO_LOADS``
#: (``session-manager-list.ts:19``).
_MAX_CONCURRENT_SESSION_INFO_LOADS = 10


# ============================================================================
# Header read
# ============================================================================


def _read_first_session_file_line(file_path: str) -> Optional[str]:
    """Read the first line of a session file.

    Mirrors ``readFirstSessionFileLine``
    (``session-manager-list.ts:21-46``). Reads
    up to ``_MAX_SESSION_HEADER_BYTES`` in
    ``_SESSION_HEADER_READ_CHUNK_BYTES`` chunks;
    stops as soon as it finds a ``\\n``.
    """
    try:
        with open(file_path, "rb") as f:
            chunks: list[bytes] = []
            total_bytes = 0
            while total_bytes < _MAX_SESSION_HEADER_BYTES:
                buffer = bytearray(
                    min(
                        _SESSION_HEADER_READ_CHUNK_BYTES,
                        _MAX_SESSION_HEADER_BYTES - total_bytes,
                    )
                )
                bytes_read = f.readinto(buffer)
                if bytes_read == 0:
                    break
                newline_index = buffer.find(0x0A)
                if 0 <= newline_index < bytes_read:
                    chunks.append(bytes(buffer[:newline_index]))
                    return b"".join(chunks).decode("utf-8", errors="replace")
                chunks.append(bytes(buffer[:bytes_read]))
                total_bytes += bytes_read
            return (
                b"".join(chunks).decode("utf-8", errors="replace")
                if chunks
                else None
            )
    except (OSError, FileNotFoundError):
        return None


def _read_session_header_from_file(
    file_path: str,
) -> Optional[SessionHeader]:
    """Read + parse the session header.

    Mirrors ``readSessionHeaderFromFile``
    (``session-manager-list.ts:48-59``). Returns
    ``None`` when the file is missing, the first
    line is empty, or the header is malformed.
    """
    first_line = _read_first_session_file_line(file_path)
    if not first_line:
        return None
    try:
        header = json.loads(first_line)
    except (ValueError, TypeError):
        return None
    if not isinstance(header, dict):
        return None
    if header.get("type") != "session":
        return None
    if not isinstance(header.get("id"), str):
        return None
    return header  # type: ignore[return-value]


# ============================================================================
# findMostRecentSession
# ============================================================================


def find_most_recent_session(
    session_dir: str, cwd: Optional[str] = None
) -> Optional[str]:
    """Return the path to the most recently
    modified session file.

    Mirrors ``findMostRecentSession``
    (``session-manager-list.ts:61-77``). Returns
    ``None`` when the directory doesn't exist or
    contains no session files.
    """
    try:
        if not os.path.isdir(session_dir):
            return None
        candidates: list[dict] = []
        for filename in os.listdir(session_dir):
            if not filename.endswith(".jsonl"):
                continue
            full_path = os.path.join(session_dir, filename)
            header = _read_session_header_from_file(full_path)
            if header is None:
                continue
            if cwd is not None and header.get("cwd") != cwd:
                continue
            try:
                mtime = os.stat(full_path).st_mtime
            except (OSError, FileNotFoundError):
                continue
            candidates.append({"path": full_path, "mtime": mtime})
        # Sort by mtime descending; the most recent
        # wins. The OpenClaw source uses
        # ``toSorted`` (a TS 5+ Array method); the
        # Python port uses ``sorted(..., reverse=True)``.
        candidates.sort(key=lambda c: c["mtime"], reverse=True)
        return candidates[0]["path"] if candidates else None
    except (OSError, FileNotFoundError):
        return None


# ============================================================================
# Text extraction
# ============================================================================


def _is_message_with_content(message: Any) -> bool:
    """True iff ``message`` is a message with a
    ``content`` field. Mirrors the private
    ``isMessageWithContent``
    (``session-manager-list.ts:79-81``).
    """
    return (
        isinstance(message, dict)
        and isinstance(message.get("role"), str)
        and "content" in message
    )


def _extract_text_content(message: dict) -> str:
    """Extract the text content of a message.

    Mirrors ``extractTextContent``
    (``session-manager-list.ts:83-91``).
    """
    content = message.get("content")
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    text_parts: list[str] = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "text":
            text_parts.append(str(block.get("text", "")))
    return " ".join(text_parts)


def _get_last_activity_time(entries: list[FileEntry]) -> Optional[int]:
    """Return the most recent activity timestamp
    in ``entries`` (epoch ms). Mirrors the private
    ``getLastActivityTime``
    (``session-manager-list.ts:93-120``).
    """
    last_activity: Optional[int] = None
    for entry in entries:
        if not isinstance(entry, dict) or entry.get("type") != "message":
            continue
        message = entry.get("message")
        if not _is_message_with_content(message):
            continue
        role = message.get("role")
        if role != "user" and role != "assistant":
            continue
        # Prefer the per-message ``timestamp`` (ms).
        per_message_timestamp = message.get("timestamp")
        if isinstance(per_message_timestamp, (int, float)):
            per_message_timestamp = int(per_message_timestamp)
            last_activity = (
                per_message_timestamp
                if last_activity is None
                else max(last_activity, per_message_timestamp)
            )
            continue
        # Fall back to the entry-level ISO timestamp.
        entry_timestamp = entry.get("timestamp")
        if isinstance(entry_timestamp, str):
            try:
                # The OpenClaw source uses
                # ``new Date(entryTimestamp).getTime()``
                # which interprets ISO 8601 strings.
                # ``datetime.fromisoformat`` is the
                # closest equivalent but doesn't
                # accept the trailing ``Z``. Strip
                # the ``Z`` and assume UTC.
                iso = entry_timestamp.replace("Z", "+00:00")
                ts = datetime.fromisoformat(iso).timestamp() * 1000
                last_activity = (
                    int(ts)
                    if last_activity is None
                    else max(last_activity, int(ts))
                )
            except (ValueError, TypeError):
                pass
    return last_activity


def _get_session_modified_date(
    entries: list[FileEntry],
    header: SessionHeader,
    stats_mtime: datetime,
) -> datetime:
    """Return the session's most recent activity
    time. Mirrors ``getSessionModifiedDate``
    (``session-manager-list.ts:122-134``)."""
    last_activity = _get_last_activity_time(entries)
    if last_activity is not None and last_activity > 0:
        return datetime.fromtimestamp(last_activity / 1000.0)
    header_timestamp = header.get("timestamp") if isinstance(header, dict) else None
    if isinstance(header_timestamp, str):
        try:
            iso = header_timestamp.replace("Z", "+00:00")
            return datetime.fromisoformat(iso)
        except (ValueError, TypeError):
            pass
    return stats_mtime


# ============================================================================
# buildSessionInfo
# ============================================================================


def _build_session_info(file_path: str) -> Optional[SessionInfo]:
    """Build a :class:`SessionInfo` from a session
    file path. Mirrors ``buildSessionInfo``
    (``session-manager-list.ts:136-206``).

    The OpenClaw source is ``async`` (it uses
    ``readFile`` / ``stat`` from
    ``node:fs/promises``). The Python port keeps
    the public ``async`` surface (the
    ``listSessions`` / ``listAllSessions`` callers
    await the result) but uses synchronous file
    IO inside a thread pool so the event loop is
    not blocked.
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
    except (OSError, FileNotFoundError):
        return None

    entries: list[FileEntry] = []
    skipped = 0
    for line in content.strip().split("\n"):
        if not line.strip():
            continue
        try:
            entries.append(json.loads(line))
        except (ValueError, TypeError):
            skipped += 1
    if skipped > 0:
        _LOG.warning(
            "buildSessionInfo: skipped %d malformed JSONL line(s) in %s — "
            "%d valid entries were loaded",
            skipped,
            file_path,
            len(entries),
        )
    if not entries:
        return None
    header = entries[0]
    if not isinstance(header, dict) or header.get("type") != "session":
        return None

    try:
        stat = os.stat(file_path)
        stats_mtime = datetime.fromtimestamp(stat.st_mtime)
    except (OSError, FileNotFoundError):
        return None

    message_count = 0
    first_message: Optional[str] = None
    all_messages: list[str] = []
    name: Optional[str] = None
    for entry in entries:
        if isinstance(entry, dict):
            if entry.get("type") == "session_info":
                raw_name = entry.get("name")
                if isinstance(raw_name, str):
                    name = raw_name.strip() or None
            if entry.get("type") != "message":
                continue
            message_count += 1
            message = entry.get("message")
            if not _is_message_with_content(message):
                continue
            role = message.get("role")
            if role != "user" and role != "assistant":
                continue
            text_content = _extract_text_content(message)
            if not text_content:
                continue
            all_messages.append(text_content)
            if first_message is None and role == "user":
                first_message = text_content
    return SessionInfo(
        path=file_path,
        id=header.get("id", ""),
        cwd=header.get("cwd", ""),
        name=name,
        parent_session_path=header.get("parentSession"),
        created=datetime.fromisoformat(
            header.get("timestamp", "").replace("Z", "+00:00")
        )
        if header.get("timestamp")
        else stats_mtime,
        modified=_get_session_modified_date(entries, header, stats_mtime),
        message_count=message_count,
        first_message=first_message or "(no messages)",
        all_messages_text=" ".join(all_messages),
    )


async def _build_session_info_async(file_path: str) -> Optional[SessionInfo]:
    """Async wrapper around :func:`_build_session_info`.

    Runs the synchronous file IO in a thread pool
    so the event loop is not blocked.
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _build_session_info, file_path)


# ============================================================================
# listSessionsFromDir
# ============================================================================


async def _list_sessions_from_dir(
    dir_path: str,
    on_progress: Optional[SessionListProgress] = None,
    progress_offset: int = 0,
    progress_total: Optional[int] = None,
    cwd: Optional[str] = None,
) -> list[SessionInfo]:
    """List all sessions in a single directory.

    Mirrors ``listSessionsFromDir``
    (``session-manager-list.ts:208-242``).
    """
    if not os.path.isdir(dir_path):
        return []
    try:
        files: list[str] = []
        for filename in os.listdir(dir_path):
            if not filename.endswith(".jsonl"):
                continue
            files.append(os.path.join(dir_path, filename))
    except (OSError, FileNotFoundError):
        return []
    total = progress_total if progress_total is not None else len(files)
    loaded = 0
    results: list[Optional[SessionInfo]] = [None] * len(files)

    def _load(index: int) -> None:
        nonlocal loaded
        try:
            results[index] = _build_session_info(files[index])
        except (OSError, ValueError, TypeError):
            results[index] = None
        finally:
            loaded += 1
            if on_progress is not None:
                on_progress(progress_offset + loaded, total)

    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor(
        max_workers=_MAX_CONCURRENT_SESSION_INFO_LOADS
    ) as pool:
        await asyncio.gather(
            *(loop.run_in_executor(pool, _load, i) for i in range(len(files)))
        )
    sessions = [r for r in results if r is not None]
    if cwd is not None:
        sessions = [s for s in sessions if s.cwd == cwd]
    return sessions


# ============================================================================
# listSessions
# ============================================================================


async def list_sessions(
    cwd: str,
    session_dir: str,
    on_progress: Optional[SessionListProgress] = None,
) -> list[SessionInfo]:
    """List all sessions in ``session_dir`` for
    ``cwd``. Mirrors ``listSessions``
    (``session-manager-list.ts:244-252``).
    """
    sessions = await _list_sessions_from_dir(
        session_dir, on_progress, 0, None, cwd
    )
    # Sort by ``modified`` descending. The OpenClaw
    # source uses an in-place ``Array.sort``; the
    # Python port uses ``sorted``.
    sessions.sort(key=lambda s: s.modified, reverse=True)
    return sessions


# ============================================================================
# listAllSessions
# ============================================================================


def _sessions_dir_default() -> str:
    """Return the JARVIS sessions directory.

    Mirrors ``getSessionsDir()`` from
    ``openclaw-main/src/agents/config.js``. The
    Python port uses the JARVIS convention
    (``~/.jarvis/agents/default/sessions``).
    """
    return str(Path.home() / ".jarvis" / "agents" / "default" / "sessions")


async def list_all_sessions(
    on_progress: Optional[SessionListProgress] = None,
) -> list[SessionInfo]:
    """List every session across all session
    sub-dirs. Mirrors ``listAllSessions``
    (``session-manager-list.ts:254-296``).
    """
    sessions_dir = _sessions_dir_default()
    if not os.path.isdir(sessions_dir):
        return []
    try:
        directories: list[str] = []
        for entry in os.listdir(sessions_dir):
            full_path = os.path.join(sessions_dir, entry)
            if os.path.isdir(full_path):
                directories.append(full_path)
    except (OSError, FileNotFoundError):
        return []
    directory_files: list[list[str]] = []
    total_files = 0
    for directory in directories:
        try:
            files = [
                os.path.join(directory, name)
                for name in os.listdir(directory)
                if name.endswith(".jsonl")
            ]
            directory_files.append(files)
            total_files += len(files)
        except (OSError, FileNotFoundError):
            directory_files.append([])
    flat_files = [f for files in directory_files for f in files]

    sessions: list[Optional[SessionInfo]] = [None] * len(flat_files)
    loaded = 0

    def _load(index: int) -> None:
        nonlocal loaded
        try:
            sessions[index] = _build_session_info(flat_files[index])
        except (OSError, ValueError, TypeError):
            sessions[index] = None
        finally:
            loaded += 1
            if on_progress is not None:
                on_progress(loaded, total_files)

    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor(
        max_workers=_MAX_CONCURRENT_SESSION_INFO_LOADS
    ) as pool:
        await asyncio.gather(
            *(loop.run_in_executor(pool, _load, i) for i in range(len(flat_files)))
        )
    result = [s for s in sessions if s is not None]
    result.sort(key=lambda s: s.modified, reverse=True)
    return result


__all__ = [
    "_MAX_CONCURRENT_SESSION_INFO_LOADS",
    "_MAX_SESSION_HEADER_BYTES",
    "_SESSION_HEADER_READ_CHUNK_BYTES",
    "find_most_recent_session",
    "list_all_sessions",
    "list_sessions",
]
