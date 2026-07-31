"""jarvis.agents.sessions.tools.bash_operations — minimal shell execution interface.

OpenClaw parity: mirrors
``openclaw-main/src/agents/sessions/tools/bash-operations.ts``.

Phase 6.10d — BashOperations interface.

The bash tool calls into a ``BashOperations``
instance for the actual shell execution. The
host injects the operations via DI (the
in-process default exec lands in
:mod:`jarvis.agents.sessions.exec`; remote
/ container / SSH use a custom implementation).

Adaptations
-----------
- The OpenClaw source uses a TS interface
  + ``NodeJS.ProcessEnv`` type. The Python
  port uses :class:`typing.Protocol` for
  the interface + :class:`os.environ`-like
  ``Mapping[str, str]`` for ``env``.
- The OpenClaw source's ``Buffer`` callback
  becomes :class:`bytes` callback (Python
  passes raw bytes; consumers decode).
- The OpenClaw source's ``AbortSignal``
  becomes :class:`threading.Event` (Phase 6.5
  pattern).
"""
from __future__ import annotations

from typing import Any, Callable, Mapping, Optional, Protocol, runtime_checkable


#: Per-chunk data callback. The shell exec
#: stream emits raw bytes (the host decodes
#: with the same UTF-8 strategy as the
#: OpenClaw source's streaming binary
#: output sanitizer).
OnData = Callable[[bytes], None]


@runtime_checkable
class BashOperations(Protocol):
    """Minimal shell execution interface
    injected into the bash tool. Mirrors
    ``BashOperations``
    (``bash-operations.ts:4-14``)."""

    def exec(
        self,
        command: str,
        cwd: str,
        options: dict,
    ) -> "Any":
        """Execute ``command`` in ``cwd`` with
        the given options. Returns an awaitable
        resolving to ``{"exitCode": int | None}``.

        The OpenClaw source's options shape
        is ``{onData, signal?, timeout?, env?}``.
        The Python port preserves the same
        dict shape.
        """
        ...


#: Convenience Protocol-with-explicit-fields
#: for callers that prefer a typed shape.
class BashExecOptions(dict):
    """Convenience dict shape for the bash
    exec options. The OpenClaw source's
    options object literal maps cleanly to
    a plain dict."""

    onData: OnData
    signal: Optional[Any]
    timeout: Optional[int]
    env: Optional[Mapping[str, str]]


__all__ = [
    "BashExecOptions",
    "BashOperations",
    "OnData",
]
