"""jarvis.agents.sessions.bash_executor — bash command execution.

OpenClaw parity: mirrors
``openclaw-main/src/agents/sessions/bash-executor.ts``.

Bash command execution with streaming support and
cancellation. This module is the shared implementation
used by ``AgentSession.execute_bash`` (Phase 6.12) and
RPC modes.

Parity
======
- ``BashExecutorOptions`` dataclass
  (``bash-executor.ts:17-22``): ``on_chunk?``,
  ``signal?``.
- ``BashResult`` dataclass (``bash-executor.ts:24-35``):
  ``output``, ``exit_code?`` (None when cancelled),
  ``cancelled``, ``truncated``,
  ``full_output_path?`` (path to the temp file
  holding the full output when truncation kicked in).
- ``execute_bash_with_operations(command, cwd, operations, options?)``
  (``bash-executor.ts:45-104``) — runs the bash
  command through a custom ``BashOperations``
  instance (used for remote / SSH / container
  execution). The local-execution path lands in
  Phase 6.10 (built-in tools) which wires the
  in-process ``exec_command`` from
  :mod:`jarvis.agents.sessions.exec`.

Phase 6.1 — storage primitives.

Adaptations
-----------
- ``BashOperations`` and ``OutputAccumulator`` are
  declared as ``Protocol`` types in Phase 6.1 so the
  :func:`execute_bash_with_operations` signature is
  stable before the real implementations land in
  Phase 6.10.
- ``create_streaming_binary_output_sanitizer`` is
  declared in the ``shell-utils`` port (Phase 6.1
  ships a local stub that strips ``\\r`` and replaces
  NUL / control chars — full binary sanitization
  lands in Phase 6.10 alongside the built-in tools).
"""
from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from typing import Callable, Optional, Protocol, runtime_checkable


# ============================================================================
# Types — mirror bash-executor.ts:13-35
# ============================================================================


@dataclass
class BashExecutorOptions:
    """Mirrors ``BashExecutorOptions``
    (``bash-executor.ts:17-22``)."""

    on_chunk: Optional[Callable[[str], None]] = None
    signal: Optional[asyncio.Event] = None


@dataclass
class BashResult:
    """Mirrors ``BashResult`` (``bash-executor.ts:24-35``)."""

    output: str
    exit_code: Optional[int]
    cancelled: bool
    truncated: bool
    full_output_path: Optional[str] = None


# ============================================================================
# Streaming binary output sanitizer
# ============================================================================
#
# The OpenClaw source imports
# ``createStreamingBinaryOutputSanitizer`` from
# ``../shell-utils.js``. Phase 6.1 ships a local
# helper that strips ``\r`` and replaces NUL /
# other non-printable control chars with ``?``. The
# full sanitizer (binary detection, encoding
# fallback) lands in Phase 6.10.
#
# Note: the Phase 6.1 implementation is a "good
# enough" sanitizer for tests + first consumer; the
# Phase 6.10 port replaces the body with the
# OpenClaw-equivalent logic verbatim.
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def create_streaming_binary_output_sanitizer() -> Callable[[str], str]:
    """Return a streaming sanitizer function. Mirrors
    ``createStreamingBinaryOutputSanitizer``
    (imported in ``bash-executor.ts:9``).

    The Phase 6.1 implementation:
    - Strips ``\r`` (matches the OpenClaw
      ``sanitizeOutput(...).replace(/\\r/g, "")``
      call in ``bash-executor.ts:54``).
    - Replaces NUL / control characters with ``?``
      to keep the model context printable.

    Returns
    -------
    Callable[[str], str]
        A function that takes a chunk of decoded
        text and returns the sanitized version.
    """

    def sanitize(text: str) -> str:
        text = text.replace("\r", "")
        text = _CONTROL_CHARS_RE.sub("?", text)
        return text

    return sanitize


# ============================================================================
# BashOperations protocol
# ============================================================================


@runtime_checkable
class BashOperations(Protocol):
    """Mirror of ``BashOperations`` (used by
    ``bash-executor.ts:11`` via the in-Phase-6.10
    ``tools/bash-operations.ts`` port). The concrete
    implementation lands in Phase 6.10.

    The protocol keeps the Phase 6.1 surface
    importable so callers can type-hint
    ``execute_bash_with_operations`` without a
    circular import.
    """

    async def exec(
        self,
        command: str,
        cwd: str,
        options: dict,
    ) -> "BashOperationsExecResult":
        ...


@dataclass
class BashOperationsExecResult:
    """Subset of the ``BashOperations.exec`` return
    shape that ``execute_bash_with_operations``
    consumes (``bash-executor.ts:89-104``). The
    full shape lands in Phase 6.10.
    """

    exit_code: Optional[int] = None


# ============================================================================
# Output accumulator stub
# ============================================================================
#
# The OpenClaw source uses ``OutputAccumulator`` from
# ``./tools/output-accumulator.js``. Phase 6.10
# ports the real implementation; Phase 6.1 ships a
# minimal in-memory accumulator that satisfies the
# shape ``execute_bash_with_operations`` requires
# (so the function can be tested without depending
# on the full Phase 6.10 surface).


@dataclass
class _OutputSnapshot:
    content: str
    full_output_path: Optional[str] = None


class OutputAccumulator:
    """Minimal in-memory accumulator. Mirrors the
    *shape* of OpenClaw's
    ``./tools/output-accumulator.js`` ; the full
    streaming + temp-file logic lands in Phase 6.10.

    Methods used by ``execute_bash_with_operations``:
    - ``append(data: bytes) -> str`` — append a chunk
      of decoded text, return the *new* text since
      the last snapshot.
    - ``finish() -> str`` — final flush.
    - ``snapshot(persist_if_truncated=True) -> _OutputSnapshot``
    - ``close_temp_file()`` — no-op in Phase 6.1
      (the temp file is wired in Phase 6.10).
    """

    def __init__(
        self,
        *,
        temp_file_prefix: str = "openclaw-bash",
        transform_decoded_text: Optional[Callable[[str], str]] = None,
    ) -> None:
        self._temp_file_prefix = temp_file_prefix
        self._transform = transform_decoded_text
        self._buffer: list[str] = []
        self._total_decoded = ""
        self._closed = False
        self._truncated = False
        self._full_output_path: Optional[str] = None

    def append(self, data: bytes) -> str:
        if self._closed:
            return ""
        text = data.decode("utf-8", errors="replace")
        if self._transform is not None:
            text = self._transform(text)
        # The new chunk's text is the entire decoded
        # payload (not a delta against the cumulative).
        # The cumulative is still tracked so a Phase
        # 6.10 ``text`` re-decode can detect a
        # mid-multibyte boundary, but for the
        # accumulator the new text is the whole
        # chunk.
        new = text
        self._total_decoded = (self._total_decoded or "") + text
        self._buffer.append(new)
        return new

    def finish(self) -> str:
        if self._closed:
            return ""
        result = "".join(self._buffer)
        self._closed = True
        return result

    def snapshot(self, *, persist_if_truncated: bool = True) -> _OutputSnapshot:
        return _OutputSnapshot(
            content="".join(self._buffer),
            full_output_path=self._full_output_path,
        )

    async def close_temp_file(self) -> None:
        # Phase 6.10 wires the temp-file lifecycle; for
        # now this is a no-op.
        return None


# ============================================================================
# execute_bash_with_operations
# ============================================================================


async def execute_bash_with_operations(
    command: str,
    cwd: str,
    operations: BashOperations,
    options: Optional[BashExecutorOptions] = None,
) -> BashResult:
    """Execute a bash command via a ``BashOperations``
    instance. Mirrors ``executeBashWithOperations``
    (``bash-executor.ts:45-104``).

    Used for remote execution (SSH, containers, etc.)
    where the command runs through a custom operations
    class rather than the local
    :func:`jarvis.agents.sessions.exec.exec_command`.

    Parameters
    ----------
    command : str
        Bash command to execute.
    cwd : str
        Working directory.
    operations : BashOperations
        The execution backend. Phase 6.10 ports the
        real ``LocalBashOperations`` + remote
        variants; Phase 6.1 ships the protocol so
        this function is importable + testable.
    options : BashExecutorOptions | None
        Optional streaming / cancellation hooks.

    Returns
    -------
    BashResult
        The captured output, exit code, and
        truncation / cancellation flags.
    """
    options = options or BashExecutorOptions()
    sanitize_output = create_streaming_binary_output_sanitizer()
    output = OutputAccumulator(
        temp_file_prefix="openclaw-bash",
        transform_decoded_text=lambda text: sanitize_output(text).replace("\r", ""),
    )

    def on_data(data: bytes) -> None:
        text = output.append(data)
        if options.on_chunk is not None:
            options.on_chunk(text)

    async def finalize_output() -> _OutputSnapshot:
        final_text = output.finish()
        snapshot = output.snapshot(persist_if_truncated=True)
        try:
            if final_text and options.on_chunk is not None:
                options.on_chunk(final_text)
            return snapshot
        finally:
            await output.close_temp_file()

    async def build_result(
        exit_code: Optional[int],
        cancelled: bool,
    ) -> BashResult:
        snapshot = await finalize_output()
        return BashResult(
            output=snapshot.content,
            exit_code=None if cancelled else exit_code,
            cancelled=cancelled,
            truncated=False,  # Phase 6.10 wires the real flag
            full_output_path=snapshot.full_output_path,
        )

    try:
        result = await operations.exec(
            command, cwd, {"on_data": on_data, "signal": options.signal}
        )
    except Exception:
        if options.signal is not None and options.signal.is_set():
            return await build_result(None, True)
        await finalize_output()
        raise

    cancelled = options.signal is not None and options.signal.is_set()
    return await build_result(result.exit_code, cancelled)


__all__ = [
    "BashExecutorOptions",
    "BashOperations",
    "BashOperationsExecResult",
    "BashResult",
    "OutputAccumulator",
    "create_streaming_binary_output_sanitizer",
    "execute_bash_with_operations",
]
