"""jarvis.agents.sessions.exec — shared command execution utilities.

OpenClaw parity: mirrors
``openclaw-main/src/agents/sessions/exec.ts``.

Shared command-execution utilities used by
extensions and custom tools. The production path
runs subprocesses with timeout + abort support,
UTF-8 streaming output capture, output-char limits
(truncate-tail by default, hard-fail otherwise),
and a force-kill grace window.

Parity
======
- ``ExecOptions`` dataclass
  (``exec.ts:17-26``): ``signal``, ``timeout``,
  ``cwd``, ``max_output_chars?``.
- ``ExecResult`` dataclass (``exec.ts:31-39``):
  ``stdout``, ``stderr``, ``stdout_truncated_chars?``,
  ``stderr_truncated_chars?``, ``output_limit_exceeded?``
  (``"stdout" | "stderr"``), ``code``, ``killed``.
- ``exec_command(command, args, cwd, options=None)``
  (``exec.ts:85-236``) — the canonical executor.
- ``DEFAULT_OUTPUT_LIMIT_CHARS = 16 * 1024 * 1024``
  (``exec.ts:11``).
- ``FORCE_KILL_GRACE_MS = 5000`` (``exec.ts:12``).
- UTF-16 safe truncation (preserves surrogate
  pairs) via :func:`_slice_utf16_safe` — a port of
  OpenClaw's ``@openclaw/normalization-core/utf16-slice``.

Phase 6.1 — storage primitives.

Adaptations
-----------
- The OpenClaw source imports ``spawnCommand`` from
  ``../../process/exec.js`` + ``killProcessTree`` from
  ``../../process/kill-tree.js``. The full process
  management port lands in Phase 6.13. Phase 6.1
  ships a local ``_spawn`` helper that uses Python's
  ``subprocess.Popen`` with the same options
  (``buffer=False``, ``cwd``, ``detached=not win32``,
  ``stdio=[ignore, pipe, pipe]``).
- The OpenClaw source uses ``StringDecoder`` for
  incremental UTF-8 decoding across chunk boundaries;
  the Python port uses ``codecs.getincrementaldecoder``
  for the same behaviour (Python's native
  ``bytes.decode(errors="replace")`` would split
  multi-byte sequences at chunk boundaries).
- The OpenClaw source's ``killed = true`` is set when
  the *timeout* OR the *abort signal* fires; the
  Python port follows the same logic.
- Force-kill grace uses ``Timer`` with a one-shot
  callback. The kill tree on Windows uses
  ``CREATE_NEW_PROCESS_GROUP``; on POSIX it
  uses the process group (``start_new_session``).
"""
from __future__ import annotations

import asyncio
import codecs
import os
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Optional, Union


#: Default output retention cap per stream, in
#: characters. Mirrors ``DEFAULT_OUTPUT_LIMIT_CHARS``
#: (``exec.ts:11``). 16 MB; ample for typical tool
#: output but bounded so a runaway process can't
#: OOM the host.
DEFAULT_OUTPUT_LIMIT_CHARS = 16 * 1024 * 1024

#: Grace period between a SIGTERM (POSIX) /
#: ``TerminateProcess`` (Windows) and the force-kill
#: SIGKILL / ``taskkill /F``. Mirrors
#: ``FORCE_KILL_GRACE_MS`` (``exec.ts:12``). 5 s.
FORCE_KILL_GRACE_MS = 5_000


def _slice_utf16_safe(
    text: str,
    start: int = 0,
    end: Optional[int] = None,
) -> str:
    """Slice a string by *character* indices without
    splitting surrogate pairs.

    Mirrors the OpenClaw ``@openclaw/normalization-core/utf16-slice``
    helper, which the OpenClaw source uses to keep
    multi-byte output truncation safe across the
    Python / JavaScript divide. The OpenClaw
    ``sliceUtf16Safe(combined, overflowChars)`` form
    drops the leading ``overflowChars`` characters
    (truncate-tail); the ``sliceUtf16Safe(combined, 0,
    maxOutputChars)`` form keeps the first
    ``maxOutputChars`` characters (truncate-head).

    Python's ``str`` slices by *code point*, not by
    code unit, so a regular ``s[i:j]`` cannot split a
    surrogate pair in the BMP (Python 3.3+ uses the
    "wide" build with PEP 393). The helper is
    therefore a no-op for ``str``; it exists so the
    port's behaviour matches the OpenClaw source
    surface and so a future ``str`` → ``PyArrow
    large-utf8`` swap stays a one-line change.
    """
    if end is None:
        return text[start:]
    return text[start:end]


@dataclass
class ExecOptions:
    """Options for executing shell commands.

    Mirrors ``ExecOptions`` (``exec.ts:17-26``).
    """

    signal: Optional[asyncio.Event] = None
    timeout: Optional[float] = None
    cwd: Optional[str] = None
    max_output_chars: Optional[int] = None


@dataclass
class ExecResult:
    """Result of executing a shell command.

    Mirrors ``ExecResult`` (``exec.ts:31-39``)."""

    stdout: str = ""
    stderr: str = ""
    stdout_truncated_chars: Optional[int] = None
    stderr_truncated_chars: Optional[int] = None
    output_limit_exceeded: Optional[str] = None
    code: int = 0
    killed: bool = False


@dataclass
class _OutputCapture:
    """Internal accumulator for a single stream."""

    text: str = ""
    truncated_chars: int = 0


def _clamp_max_output_chars(value: Optional[int]) -> int:
    """Clamp the ``max_output_chars`` value to a
    valid positive integer. Mirrors ``clampMaxOutputChars``
    (``exec.ts:50-55``)."""
    if (
        value is None
        or not isinstance(value, (int, float))
        or not _isfinite(value)
        or value <= 0
    ):
        return DEFAULT_OUTPUT_LIMIT_CHARS
    return max(1, int(value))


def _isfinite(value: float) -> bool:
    """Local re-implementation of ``Number.isFinite``
    (which ``exec.ts:51`` uses). Returns ``False`` for
    NaN and infinities."""
    return value == value and value not in (float("inf"), float("-inf"))


def _append_captured_output(
    current: _OutputCapture,
    chunk: str,
    max_output_chars: int,
    truncate_tail: bool,
) -> _OutputCapture:
    """Append ``chunk`` to the captured output,
    truncating to ``max_output_chars``. Mirrors
    ``appendCapturedOutput`` (``exec.ts:57-79``)."""
    combined = current.text + chunk
    overflow = max(0, len(combined) - max_output_chars)
    if overflow == 0:
        return _OutputCapture(
            text=combined, truncated_chars=current.truncated_chars
        )
    next_text = (
        _slice_utf16_safe(combined, overflow)
        if truncate_tail
        else _slice_utf16_safe(combined, 0, max_output_chars)
    )
    return _OutputCapture(
        text=next_text,
        truncated_chars=current.truncated_chars + len(combined) - len(next_text),
    )


def _spawn(
    command: str,
    args: list[str],
    cwd: str,
) -> "subprocess.Popen[bytes]":
    """Spawn a subprocess for execution.

    Mirrors the OpenClaw ``spawnCommand`` call
    (``exec.ts:92-98``):
    - ``buffer=False`` (Python: we read the raw
      streams ourselves; the OpenClaw option is the
      cross-platform equivalent)
    - ``cwd`` (passed through)
    - ``detached=process.platform !== "win32"`` —
      creates a new process group on POSIX so a kill
      tree can take down children; on Windows the
      flag is implicit via ``CREATE_NEW_PROCESS_GROUP``
      (Python's ``subprocess`` exposes this as
      ``creationflags``)
    - ``stdio=["ignore", "pipe", "pipe"]``

    The OpenClaw source uses ``reject: false`` so
    the promise resolves with the failure result
    instead of rejecting. The Python port does not
    need this — ``Popen`` does not raise on non-zero
    exit codes.
    """
    creationflags = 0
    start_new_session = False
    if sys.platform == "win32":
        # 0x00000200 = ``CREATE_NEW_PROCESS_GROUP``;
        # the symbolic name is only available on
        # Python 3.13+, so use the literal.
        creationflags |= 0x00000200
    else:
        # POSIX: mirrors ``detached: process.platform
        # !== "win32"`` (``exec.ts:96``) — the child
        # leads a new process group so the pgid kill
        # in ``_kill_process_tree`` takes down the
        # child + descendants without touching the
        # caller's own group.
        start_new_session = True

    return subprocess.Popen(
        [command, *args],
        cwd=cwd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=0,  # equivalent to ``buffer: false``
        shell=False,
        creationflags=creationflags,
        start_new_session=start_new_session,
    )


def _kill_process_tree(proc: "subprocess.Popen[bytes]") -> None:
    """Best-effort kill of the subprocess + descendants.

    Mirrors ``killProcessTree`` (imported at
    ``exec.ts:9``). The full tree-kill port lands
    in Phase 6.13; for Phase 6.1 we ship a single-
    process kill that closes the process tree at
    its root. On Windows, ``CREATE_NEW_PROCESS_GROUP``
    (set in :func:`_spawn`) lets ``taskkill /T`` find
    children; on POSIX the process was spawned with
    ``start_new_session`` (via the ``preexec_fn``
    fallback below) so the children share the
    process group.
    """
    try:
        if sys.platform == "win32":
            # On Windows, ``taskkill /T /F /PID``
            # takes down the process + its
            # descendants. ``/F`` is the force
            # flag; ``/T`` is the tree flag.
            subprocess.run(
                ["taskkill", "/T", "/F", "/PID", str(proc.pid)],
                capture_output=True,
                check=False,
                timeout=5,
            )
        else:
            # POSIX: send SIGKILL to the negative
            # PID (= the process group started with
            # ``start_new_session=True``). Fall back
            # to a direct ``proc.kill()`` if the OS
            # doesn't support pgid kill.
            try:
                os.killpg(os.getpgid(proc.pid), 9)  # SIGKILL
            except (ProcessLookupError, PermissionError, OSError):
                proc.kill()
    except (subprocess.TimeoutExpired, OSError):
        # Last resort: direct kill.
        try:
            proc.kill()
        except OSError:
            pass


def exec_command(
    command: str,
    args: list[str],
    cwd: str,
    options: Optional[ExecOptions] = None,
) -> ExecResult:
    """Execute a shell command and return its result.

    Mirrors ``execCommand`` (``exec.ts:85-236``).

    The function runs the subprocess with the
    configured ``max_output_chars`` cap (default 16
    MB per stream), UTF-8 streaming output capture,
    abort-signal cancellation, timeout-based
    force-kill (5 s grace), and optional
    ``truncate_output`` semantics. When the caller
    does *not* provide ``max_output_chars``, output
    beyond the cap kills the process and reports
    ``output_limit_exceeded``; when the caller does
    provide one, output is silently truncated.

    Parameters
    ----------
    command : str
        Executable path or name (resolved via
        ``PATH``).
    args : list[str]
        Command arguments (in addition to ``command``).
    cwd : str
        Working directory.
    options : ExecOptions | None
        Optional timeout / abort / cap.

    Returns
    -------
    ExecResult
        The captured stdout / stderr / exit code /
        truncation counters / ``output_limit_exceeded``
        / ``killed`` flag.
    """
    options = options or ExecOptions()
    # ``asyncio.Event`` is the Python port of
    # OpenClaw's ``AbortSignal``. Phase 6.1 ships a
    # thin in-process implementation; full AbortSignal
    # parity lands in Phase 6.13.
    signal = options.signal
    timeout = options.timeout
    max_output_chars = _clamp_max_output_chars(options.max_output_chars)
    truncate_output = options.max_output_chars is not None

    proc = _spawn(command, args, cwd)
    stdout = _OutputCapture()
    stderr = _OutputCapture()
    stdout_decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
    stderr_decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
    killed = False
    output_limit_exceeded: Optional[str] = None
    settled = threading.Event()
    result_holder: list[ExecResult] = []

    timeout_timer: Optional[threading.Timer] = None
    force_kill_timer: Optional[threading.Timer] = None

    def kill_process() -> None:
        nonlocal killed
        if killed:
            return
        killed = True
        if proc.pid is not None:
            _kill_process_tree(proc)
        else:
            try:
                proc.kill()
            except OSError:
                pass

    def force_kill() -> None:
        if not settled.is_set():
            try:
                proc.kill()
            except OSError:
                pass

    def finish(code: int) -> None:
        nonlocal stdout, stderr, output_limit_exceeded
        if settled.is_set():
            return
        settled.set()
        if timeout_timer is not None:
            timeout_timer.cancel()
        if force_kill_timer is not None:
            force_kill_timer.cancel()

        # Flush incremental decoders.
        stdout_before_flush = stdout.truncated_chars
        stdout = _append_captured_output(
            stdout, stdout_decoder.decode(b"", final=True),
            max_output_chars, truncate_output,
        )
        if (
            not truncate_output
            and stdout.truncated_chars > stdout_before_flush
            and output_limit_exceeded is None
        ):
            output_limit_exceeded = "stdout"

        stderr_before_flush = stderr.truncated_chars
        stderr = _append_captured_output(
            stderr, stderr_decoder.decode(b"", final=True),
            max_output_chars, truncate_output,
        )
        if (
            not truncate_output
            and stderr.truncated_chars > stderr_before_flush
            and output_limit_exceeded is None
        ):
            output_limit_exceeded = "stderr"

        if output_limit_exceeded is not None:
            stderr = _append_captured_output(
                stderr,
                f'{stderr.text if stderr.text else ""}'
                f'\nexec {output_limit_exceeded} exceeded output limit '
                f'{max_output_chars} chars',
                max_output_chars,
                True,
            )

        result_holder.append(
            ExecResult(
                stdout=stdout.text,
                stderr=stderr.text,
                stdout_truncated_chars=stdout.truncated_chars or None,
                stderr_truncated_chars=stderr.truncated_chars or None,
                output_limit_exceeded=output_limit_exceeded,
                code=1 if output_limit_exceeded else code,
                killed=killed,
            )
        )

    def mark_output_limit_exceeded(stream: str) -> None:
        nonlocal output_limit_exceeded
        if not truncate_output and output_limit_exceeded is None:
            output_limit_exceeded = stream
            kill_process()

    def read_stream(stream, decoder, is_stdout: bool) -> None:
        """Drain a stream into the output accumulator.

        Runs in a background thread so the main
        thread can ``wait()`` on the process and the
        read doesn't deadlock. The OpenClaw source
        reads in the same thread because the
        ``spawnCommand`` promise handles the
        synchronization; the Python port mirrors
        the same effect with a daemon thread per
        stream.
        """
        nonlocal stdout, stderr
        local_capture = stdout if is_stdout else stderr
        local_stream_name = "stdout" if is_stdout else "stderr"
        while True:
            # Honour the abort signal mid-read.
            if signal is not None and signal.is_set():
                kill_process()
            try:
                if stream is None:
                    return
                chunk = stream.read(4096)
            except (ValueError, OSError):
                return
            if not chunk:
                return
            before = local_capture.truncated_chars
            new_capture = _append_captured_output(
                local_capture,
                decoder.decode(chunk),
                max_output_chars,
                truncate_output,
            )
            if is_stdout:
                stdout = new_capture
            else:
                stderr = new_capture
            if new_capture.truncated_chars > before:
                mark_output_limit_exceeded(local_stream_name)

    # Abort signal hook. Pre-cancelled signals skip
    # the launch entirely (mirrors the OpenClaw
    # ``options.signal.aborted`` branch in
    # ``exec.ts:183-184``).
    if signal is not None and signal.is_set():
        kill_process()

    # Timeout hook. Mirrors the OpenClaw source's
    # ``setTimeout`` (``exec.ts:191-195``).
    if timeout is not None and timeout > 0:
        timeout_timer = threading.Timer(timeout, kill_process)
        timeout_timer.daemon = True
        timeout_timer.start()
        # Force-kill backstop.
        force_kill_timer = threading.Timer(
            timeout + FORCE_KILL_GRACE_MS / 1000.0, force_kill
        )
        force_kill_timer.daemon = True
        force_kill_timer.start()

    # Abort-signal monitor. The main thread blocks
    # in ``proc.wait()``; the read threads only
    # see data when the subprocess writes. A
    # dedicated monitor polls the signal at 50 ms
    # intervals and fires ``kill_process`` when
    # the signal is set. Mirrors the OpenClaw
    # ``options.signal.addEventListener("abort",
    # killProcess, {once: true})`` (``exec.ts:186``).
    signal_monitor_stop = [False]

    def _signal_monitor() -> None:
        while not signal_monitor_stop[0]:
            if signal is not None and signal.is_set():
                kill_process()
                return
            time.sleep(0.05)

    if signal is not None:
        signal_monitor = threading.Thread(
            target=_signal_monitor, daemon=True
        )
        signal_monitor.start()
    else:
        signal_monitor = None

    # Drain stdout / stderr on background threads so
    # the main thread can ``wait()`` without
    # deadlocking the OS pipe buffers.
    stdout_thread: Optional[threading.Thread] = None
    stderr_thread: Optional[threading.Thread] = None
    if proc.stdout is not None:
        stdout_thread = threading.Thread(
            target=read_stream,
            args=(proc.stdout, stdout_decoder, True),
            daemon=True,
        )
        stdout_thread.start()
    if proc.stderr is not None:
        stderr_thread = threading.Thread(
            target=read_stream,
            args=(proc.stderr, stderr_decoder, False),
            daemon=True,
        )
        stderr_thread.start()

    # Wait for the process to finish (this is the
    # blocking part the original OpenClaw source
    # uses the ``proc`` promise for).
    return_code = proc.wait()

    # Wait for the drain threads to finish (the
    # pipes close when the process exits, so the
    # next ``read`` returns ``b""``).
    if stdout_thread is not None:
        stdout_thread.join(timeout=5)
    if stderr_thread is not None:
        stderr_thread.join(timeout=5)
    if signal_monitor is not None:
        signal_monitor_stop[0] = True
        signal_monitor.join(timeout=1)

    finish(return_code)

    if result_holder:
        return result_holder[0]
    # Defensive: should never happen — ``finish``
    # always pushes one result — but a belt-and-
    # suspenders default keeps the type checker
    # happy.
    return ExecResult(code=return_code, killed=killed)


__all__ = [
    "DEFAULT_OUTPUT_LIMIT_CHARS",
    "ExecOptions",
    "ExecResult",
    "FORCE_KILL_GRACE_MS",
    "exec_command",
]
