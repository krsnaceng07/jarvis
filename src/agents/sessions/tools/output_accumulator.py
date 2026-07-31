"""jarvis.agents.sessions.tools.output_accumulator — streaming output accumulator for tool execution.

OpenClaw parity: mirrors
``openclaw-main/src/agents/sessions/tools/output-accumulator.ts``.

Phase 6.10b — keeps bounded display tails in
memory while spilling full output to private
temp files when needed.

The Python port preserves the same public
API:
- ``__init__(options)`` — ``maxLines``,
  ``maxBytes``, ``tempFilePrefix``,
  ``transformDecodedText``
- ``append(data: bytes) -> str`` — returns the
  decoded text added in this call
- ``finish() -> str`` — drains remaining
  decoded bytes
- ``snapshot(persistIfTruncated?) -> dict``
  with ``content``, ``truncation``,
  ``fullOutputPath?``
- ``closeTempFile() -> None`` (async)
- ``getLastLineBytes() -> int``

Adaptations
-----------
- The OpenClaw source uses Node ``TextDecoder``
  for streaming UTF-8 decode. The Python
  port uses :class:`codecs.getincrementaldecoder`
  (``utf-8``) for the same chunked decode.
- The OpenClaw source's ``Buffer.byteLength``
  becomes :func:`jarvis_agent.truncate.utf8_byte_length`.
- The OpenClaw source's
  ``createPrivateTempWriteStream`` becomes
  :func:`src.agents.sessions.tools.private_temp_file.create_private_temp_write_stream`.
- The OpenClaw source's
  ``stream.once("finish")`` event pattern is
  replaced with an explicit ``close()`` call
  (the stream is an ``io.IOBase``).
"""
from __future__ import annotations

import codecs
from dataclasses import dataclass, field
from typing import IO, Callable, Optional

from jarvis_agent.truncate import TruncationResult, truncate_tail, utf8_byte_length

from .private_temp_file import create_private_temp_write_stream
from .truncate import DEFAULT_MAX_BYTES, DEFAULT_MAX_LINES


# ============================================================================
# Options + Snapshot
# ============================================================================


@dataclass
class OutputAccumulatorOptions:
    maxLines: Optional[int] = None
    maxBytes: Optional[int] = None
    tempFilePrefix: Optional[str] = None
    transformDecodedText: Optional[Callable[[str], str]] = None


@dataclass
class OutputSnapshot:
    """Mirrors ``OutputSnapshot``
    (``output-accumulator.ts:22-26``)."""

    content: str
    truncation: TruncationResult
    fullOutputPath: Optional[str] = None


# ============================================================================
# OutputAccumulator
# ============================================================================


class OutputAccumulator:
    """Incrementally tracks streaming output
    with bounded memory. Mirrors
    ``OutputAccumulator``
    (``output-accumulator.ts:39-256``).

    The OpenClaw source's ``TextDecoder``
    chunked-decode is preserved via the
    Python ``codecs.IncrementalDecoder``.
    The temp-file write stream is an
    ``io.IOBase`` (not a Node ``WriteStream``);
    callers use :meth:`close_temp_file` (async)
    to flush.
    """

    def __init__(self, options: Optional[OutputAccumulatorOptions] = None) -> None:
        options = options or OutputAccumulatorOptions()
        self._max_lines = options.maxLines or DEFAULT_MAX_LINES
        self._max_bytes = options.maxBytes or DEFAULT_MAX_BYTES
        self._max_rolling_bytes = max(self._max_bytes * 2, 1)
        self._temp_file_prefix = options.tempFilePrefix or "openclaw-output"
        self._transform = options.transformDecodedText

        # Streaming UTF-8 decoder
        self._decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")

        # Spill buffer (before temp file is open)
        self._spill_chunks: list[bytes] = []
        # Display tail
        self._tail_text = ""
        self._tail_bytes = 0
        self._tail_starts_at_line_boundary = True
        # Cumulative stats
        self._total_raw_bytes = 0
        self._total_decoded_bytes = 0
        self._completed_lines = 0
        self._total_lines = 0
        self._current_line_bytes = 0
        self._has_open_line = False
        # Finish + temp file state
        self._finished = False
        self._temp_file_path: Optional[str] = None
        self._temp_file_stream: Optional[IO[bytes]] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def append(self, data: bytes) -> str:
        """Append a chunk + return the decoded
        text. Mirrors ``append``
        (``output-accumulator.ts:70-88``)."""
        if self._finished:
            raise RuntimeError(
                "Cannot append to a finished output accumulator"
            )
        self._total_raw_bytes += len(data)
        decoded_text = self._decoder.decode(data, final=False)
        text = self._transform(decoded_text) if self._transform else decoded_text
        self._append_decoded_text(text)
        # Sanitized output (post-transform) must
        # spill exactly what callers see.
        spill_chunk = (
            text.encode("utf-8") if self._transform else data
        )
        if self._temp_file_stream is not None or self._should_use_temp_file():
            self._ensure_temp_file()
        self._append_spill_chunk(spill_chunk)
        return text

    def finish(self) -> str:
        """Drain the decoder's remaining bytes
        + flush the temp file. Returns the
        final decoded text. Mirrors ``finish``
        (``output-accumulator.ts:90-105``)."""
        if self._finished:
            return ""
        self._finished = True
        decoded_text = self._decoder.decode(b"", final=True)
        text = self._transform(decoded_text) if self._transform else decoded_text
        self._append_decoded_text(text)
        if self._transform and text:
            self._append_spill_chunk(text.encode("utf-8"))
        if self._should_use_temp_file():
            self._ensure_temp_file()
        return text

    def snapshot(
        self, persist_if_truncated: bool = False
    ) -> OutputSnapshot:
        """Return the current display tail +
        truncation metadata. Mirrors ``snapshot``
        (``output-accumulator.ts:107-135``)."""
        tail_truncation = truncate_tail(
            self._get_snapshot_text(),
            max_lines=self._max_lines,
            max_bytes=self._max_bytes,
        )
        truncated = (
            self._total_lines > self._max_lines
            or self._total_decoded_bytes > self._max_bytes
        )
        truncated_by: Optional[str] = None
        if truncated:
            tb = getattr(tail_truncation, "truncated_by", None)
            if tb is not None:
                truncated_by = tb
            elif self._total_decoded_bytes > self._max_bytes:
                truncated_by = "bytes"
            else:
                truncated_by = "lines"
        # Merge the live totals into the
        # tail-truncation metadata (the OpenClaw
        # source uses spread; the Python port
        # builds a fresh dict).
        truncation_dict = {
            "content": tail_truncation.content,
            "truncated": truncated,
            "truncatedBy": truncated_by,
            "totalLines": self._total_lines,
            "totalBytes": self._total_decoded_bytes,
            "outputLines": getattr(tail_truncation, "output_lines", 0),
            "outputBytes": getattr(tail_truncation, "output_bytes", 0),
            "lastLinePartial": getattr(tail_truncation, "last_line_partial", False),
            "firstLineExceedsLimit": getattr(
                tail_truncation, "first_line_exceeds_limit", False
            ),
            "maxLines": self._max_lines,
            "maxBytes": self._max_bytes,
        }
        if persist_if_truncated and truncated:
            self._ensure_temp_file()
        return OutputSnapshot(
            content=truncation_dict["content"],
            truncation=truncation_dict,  # type: ignore[arg-type]
            fullOutputPath=self._temp_file_path,
        )

    async def close_temp_file(self) -> None:
        """Close the temp file write stream.
        Mirrors ``closeTempFile``
        (``output-accumulator.ts:137-158``).
        The Python port uses ``os.close``-equivalent
        on the file object (no event listener
        pattern — Python's ``close()`` raises
        on error)."""
        if self._temp_file_stream is None:
            return
        stream = self._temp_file_stream
        self._temp_file_stream = None
        stream.close()

    def get_last_line_bytes(self) -> int:
        """Return the byte count of the in-progress
        (unterminated) line. Mirrors
        ``getLastLineBytes``
        (``output-accumulator.ts:160-162``)."""
        return self._current_line_bytes

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _append_decoded_text(self, text: str) -> None:
        """Update display tail + line stats.
        Mirrors ``appendDecodedText``
        (``output-accumulator.ts:164-193``)."""
        if not text:
            return
        bytes_ = utf8_byte_length(text)
        self._total_decoded_bytes += bytes_
        self._tail_text += text
        self._tail_bytes += bytes_
        if self._tail_bytes > self._max_rolling_bytes * 2:
            self._trim_tail()

        newlines = 0
        last_newline = -1
        idx = text.find("\n")
        while idx != -1:
            newlines += 1
            last_newline = idx
            idx = text.find("\n", idx + 1)
        if newlines == 0:
            self._current_line_bytes += bytes_
            self._has_open_line = True
        else:
            self._completed_lines += newlines
            tail = text[last_newline + 1 :]
            self._current_line_bytes = utf8_byte_length(tail)
            self._has_open_line = bool(tail)
        self._total_lines = self._completed_lines + (1 if self._has_open_line else 0)

    def _trim_tail(self) -> None:
        """Trim the display tail to
        ``maxRollingBytes`` while keeping
        UTF-8 boundaries. Mirrors ``trimTail``
        (``output-accumulator.ts:195-215``)."""
        text_bytes = self._tail_text.encode("utf-8")
        if len(text_bytes) <= self._max_rolling_bytes:
            self._tail_bytes = len(text_bytes)
            return
        start = len(text_bytes) - self._max_rolling_bytes
        # Roll back continuation bytes so we
        # don't split a multi-byte char.
        while start < len(text_bytes):
            byte = text_bytes[start]
            if (byte & 0xC0) != 0x80:
                break
            start += 1
        if start == 0:
            new_starts_at_line = self._tail_starts_at_line_boundary
        else:
            new_starts_at_line = text_bytes[start - 1] == 0x0A
        self._tail_starts_at_line_boundary = new_starts_at_line
        self._tail_text = text_bytes[start:].decode("utf-8", errors="replace")
        self._tail_bytes = utf8_byte_length(self._tail_text)

    def _get_snapshot_text(self) -> str:
        """Return the snapshot text. If the
        tail doesn't start at a line
        boundary, skip past the first
        newline (the OpenClaw source's
        ``getSnapshotText``;
        ``output-accumulator.ts:217-224``)."""
        if self._tail_starts_at_line_boundary:
            return self._tail_text
        first_newline = self._tail_text.find("\n")
        if first_newline == -1:
            return self._tail_text
        return self._tail_text[first_newline + 1 :]

    def _should_use_temp_file(self) -> bool:
        """Decide whether to spill full output
        to a temp file. Mirrors
        ``shouldUseTempFile``
        (``output-accumulator.ts:226-232``)."""
        return (
            self._total_raw_bytes > self._max_bytes
            or self._total_decoded_bytes > self._max_bytes
            or self._total_lines > self._max_lines
        )

    def _append_spill_chunk(self, chunk: bytes) -> None:
        """Write ``chunk`` to the temp file
        (or buffer if the file isn't open
        yet). Mirrors ``appendSpillChunk``
        (``output-accumulator.ts:234-243``)."""
        if not chunk:
            return
        if self._temp_file_stream is not None:
            self._temp_file_stream.write(chunk)
        else:
            self._spill_chunks.append(chunk)

    def _ensure_temp_file(self) -> None:
        """Open the temp file + flush buffered
        chunks. Mirrors ``ensureTempFile``
        (``output-accumulator.ts:245-256``)."""
        if self._temp_file_path is not None:
            return
        path, stream = create_private_temp_write_stream(self._temp_file_prefix)
        self._temp_file_path = path
        self._temp_file_stream = stream
        for chunk in self._spill_chunks:
            stream.write(chunk)
        self._spill_chunks = []


__all__ = [
    "OutputAccumulator",
    "OutputAccumulatorOptions",
    "OutputSnapshot",
]
