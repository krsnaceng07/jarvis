"""jarvis.trajectory.paths — path resolution and size limits for trajectory.

OpenClaw parity: mirrors ``openclaw-main/src/trajectory/paths.ts``.
"""
import os
from pathlib import Path
from typing import Optional

from src.sessions.session_transcript_runtime import parse_sqlite_session_file_marker

TRAJECTORY_RUNTIME_CAPTURE_MAX_BYTES = 10 * 1024 * 1024
TRAJECTORY_RUNTIME_FILE_MAX_BYTES = 50 * 1024 * 1024
TRAJECTORY_RUNTIME_EVENT_MAX_BYTES = 256 * 1024
TRAJECTORY_POINTER_FILE_MAX_BYTES = 64 * 1024


def safe_trajectory_session_file_name(session_id: str) -> str:
    """Sanitize the session ID for use in file names."""
    safe = "".join(c if c.isalnum() or c in "_-" else "_" for c in session_id)[:120]
    return safe if any(c.isalnum() for c in safe) else "session"


def resolve_trajectory_file_path(
    session_id: str,
    session_file: Optional[str] = None,
    env: Optional[dict[str, str]] = None,
) -> str:
    """Resolve the storage path for trajectory artifacts."""
    env_vars = env if env is not None else os.environ

    dir_override = env_vars.get("JARVIS_TRAJECTORY_DIR", "").strip()
    if dir_override:
        return str(
            Path(dir_override)
            .expanduser()
            .resolve()
            / f"{safe_trajectory_session_file_name(session_id)}.jsonl"
        )

    if not session_file:
        return str(
            Path.cwd() / f"{safe_trajectory_session_file_name(session_id)}.trajectory.jsonl"
        )

    sqlite_marker = parse_sqlite_session_file_marker(session_file)
    if sqlite_marker:
        return str(
            Path(sqlite_marker.store_path).resolve().parent
            / "trajectory"
            / f"{safe_trajectory_session_file_name(sqlite_marker.session_id)}.jsonl"
        )

    if session_file.endswith(".jsonl"):
        return f"{session_file[:-6]}.trajectory.jsonl"
    return f"{session_file}.trajectory.jsonl"


def resolve_trajectory_pointer_file_path(session_file: str) -> str:
    """Sidecar pointer naming contract for legacy trajectory paths."""
    if session_file.endswith(".jsonl"):
        return f"{session_file[:-6]}.trajectory-path.json"
    return f"{session_file}.trajectory-path.json"
