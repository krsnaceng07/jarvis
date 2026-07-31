"""jarvis.agents.sessions.tools.private_temp_file — private temporary file helper.

OpenClaw parity: mirrors
``openclaw-main/src/agents/sessions/tools/private-temp-file.ts``.

Phase 6.10b — small helper for tool output
spillover. Creates owner-only log files
without reusing predictable names.

Adaptations
-----------
- The OpenClaw source uses Node ``crypto.randomBytes``
  + ``fs.createWriteStream`` + ``os.tmpdir``.
  The Python port uses :mod:`secrets` for
  the random id + :mod:`tempfile.NamedTemporaryFile`
  + :mod:`os.open`` with ``O_CREAT|O_EXCL``
  for the atomic create-with-mode.
- The OpenClaw source's ``writePrivateTempFile``
  uses ``fs.promises.writeFile`` with
  ``{flag: "wx", mode: 0o600}``. The Python
  port preserves the same "create exclusive
  + 0o600" semantics via the
  :func:`write_private_temp_file` helper.
"""
from __future__ import annotations

import os
import secrets
import tempfile
from typing import IO, Optional


def _create_private_temp_file_path(prefix: str) -> str:
    """Build a unique file path under the
    system temp dir. Mirrors
    ``createPrivateTempFilePath``
    (``private-temp-file.ts:30-33``)."""
    id_ = secrets.token_hex(8)
    return os.path.join(tempfile.gettempdir(), f"{prefix}-{id_}.log")


def create_private_temp_write_stream(
    prefix: str,
) -> tuple[str, IO[bytes]]:
    """Open a unique write stream with
    owner-only permissions. Returns
    ``(path, stream)``. Mirrors
    ``createPrivateTempWriteStream``
    (``private-temp-file.ts:13-22``).

    The Python port uses
    :func:`os.open` with ``O_CREAT|O_EXCL``
    + ``0o600`` to atomically create the
    file with owner-only permissions, then
    wraps the fd with :class:`io.FileIO`
    so callers can ``.write()`` chunks.
    """
    file_path = _create_private_temp_file_path(prefix)
    fd = os.open(
        file_path,
        flags=os.O_CREAT | os.O_EXCL | os.O_WRONLY,
        mode=0o600,
    )
    stream: IO[bytes] = os.fdopen(fd, "wb")
    return file_path, stream


def write_private_temp_file(prefix: str, content: str) -> str:
    """Create a private temp file containing
    ``content`` + return its path. Mirrors
    ``writePrivateTempFile``
    (``private-temp-file.ts:24-28``)."""
    file_path = _create_private_temp_file_path(prefix)
    fd = os.open(
        file_path,
        flags=os.O_CREAT | os.O_EXCL | os.O_WRONLY,
        mode=0o600,
    )
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(content.encode("utf-8"))
    except Exception:
        try:
            os.unlink(file_path)
        except OSError:
            pass
        raise
    return file_path


__all__ = [
    "create_private_temp_write_stream",
    "write_private_temp_file",
]
