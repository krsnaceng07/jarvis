"""jarvis.agents.embedded_agent_runner.session_file_key — session-file key resolution.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/session-file-key.ts``.

Public surface (mirrors the OpenClaw
source):

- :func:`resolve_embedded_session_file_key` —
  resolve a stable key for a
  session transcript file.

Phase 7.0 — focused minimal port.
"""
from __future__ import annotations

import os


def resolve_embedded_session_file_key(session_file: str) -> str:
    """Resolve a stable key for a
    session transcript file. Mirrors
    :func:`resolveEmbeddedSessionFileKey`
    (``session-file-key.ts:7-21``).

    The OpenClaw source uses
    :func:`fs.realpathSync.native` to
    canonicalize the path. The Python
    port uses :func:`os.path.realpath`
    (with a fallback to the absolute
    path when the parent dir doesn't
    exist yet).
    """
    if not session_file:
        return session_file
    resolved = os.path.abspath(session_file)
    try:
        return os.path.realpath(resolved)
    except OSError:
        pass
    parent = os.path.dirname(resolved)
    try:
        return os.path.join(
            os.path.realpath(parent),
            os.path.basename(resolved),
        )
    except OSError:
        return resolved


__all__ = ["resolve_embedded_session_file_key"]
