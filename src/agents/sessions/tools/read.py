"""jarvis.agents.sessions.tools.read — read tool.

OpenClaw parity: mirrors
``openclaw-main/src/agents/sessions/tools/read.ts``.

Phase 6.10c — read tool focused port.

Ships the critical contract:
- :func:`create_read_tool` — the factory
  function returning a :data:`ToolDefinition`
  for the read tool (Python port uses the
  ``dict``-shaped :class:`ToolDefinition`).
- :func:`create_read_tool_definition` — same
  factory returning the OpenClaw-shaped
  ``ToolDefinition`` (``read.ts:329``).
- :func:`read_text_file` — the text read
  helper (read with offset/limit + truncation)
- :func:`read_image_file` — the image read
  helper (returns base64)
- :func:`detect_image_mime_type` — best-effort
  image MIME detection from extension

Adaptations
-----------
- The OpenClaw source uses TypeBox for the
  ``readSchema`` parameter schema. The
  Python port uses plain :class:`dict`
  (the JSON Schema shape lands with the
  full LLM surface in Phase 6.12+).
- The OpenClaw source's image processing
  (``processImage`` from
  ``@openclaw/media-core``) is replaced
  with a thin pass-through that returns
  the base64 data. Auto-resize lands in
  Phase 6.12+ with the media-core port.
- The OpenClaw source's
  ``defaultReadOperations`` (FS operations
  injected via DI) is replaced with direct
  :mod:`os` + :mod:`pathlib` calls. The
  operations surface (``ReadOperations``)
  lands in Phase 6.10d with the full bash
  executor refactor.
"""

from __future__ import annotations

import base64
import mimetypes
import os
from pathlib import Path
from typing import Optional

from ..extensions.types import (
    AgentToolResult,
    ToolDefinition,
)
from .path_utils import resolve_unicode_path
from .truncate import (
    DEFAULT_MAX_BYTES,
    DEFAULT_MAX_LINES,
    truncate_tail,
)


# ============================================================================
# Constants
# ============================================================================


#: Image MIME types the read tool recognises.
#: Mirrors the OpenClaw source's image-detection
#: set (read.ts).
IMAGE_MIME_TYPES: frozenset[str] = frozenset(
    {
        "image/jpeg",
        "image/png",
        "image/gif",
        "image/webp",
        "image/bmp",
    }
)


# ============================================================================
# Image MIME detection
# ============================================================================


def detect_image_mime_type(file_path: str) -> Optional[str]:
    """Best-effort image MIME type detection
    from the file extension. Mirrors the
    OpenClaw source's ``detectImageMimeType``
    hook (``read.ts``)."""
    mime, _ = mimetypes.guess_type(file_path)
    if mime is None:
        return None
    if mime.startswith("image/"):
        return mime
    return None


# ============================================================================
# Read helpers
# ============================================================================


def read_text_file(
    file_path: str,
    offset: Optional[int] = None,
    limit: Optional[int] = None,
    cwd: Optional[str] = None,
    max_lines: int = DEFAULT_MAX_LINES,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> dict:
    """Read a text file with optional offset +
    limit. Returns
    ``{"content": str, "truncation": TruncationResult?}``.

    Mirrors the text-read path of the
    OpenClaw source's ``read.ts`` execute
    function.

    Parameters
    ----------
    file_path : str
        Path to the file (resolved against
        ``cwd`` if relative).
    offset : int, optional
        1-based line number to start from
        (the OpenClaw source uses 1-indexed
        offsets; line 0 is invalid).
    limit : int, optional
        Maximum number of lines to read.
    cwd : str, optional
        Working directory for relative paths.
    max_lines, max_bytes : int
        Truncation ceilings (defaults to the
        OpenClaw shared limits).
    """
    if offset is not None and (not isinstance(offset, int) or offset < 1):
        raise ValueError("Offset must be an integer at least 1")
    resolved = resolve_unicode_path(file_path, cwd or os.getcwd())
    if not os.path.exists(resolved):
        raise FileNotFoundError(f"File not found: {resolved}")
    if os.path.isdir(resolved):
        raise IsADirectoryError(
            f"Read requires a file path, but '{resolved}' is a directory. "
            "Use 'ls' to list its contents, then read a specific file."
        )
    # Read raw bytes (we need byte-accurate
    # truncation; we decode after slicing).
    raw = Path(resolved).read_bytes()
    # Split on newlines keeping offsets
    text = raw.decode("utf-8", errors="replace")
    lines = text.splitlines()
    start = (offset - 1) if offset else 0
    if start >= len(lines):
        return {
            "content": "",
            "truncation": None,
        }
    end = start + limit if limit is not None else len(lines)
    selected = lines[start:end]
    selected_text = "\n".join(selected) + ("\n" if selected else "")
    # Apply tail truncation (the OpenClaw
    # source truncates the tail because the
    # user is reading forward; limit only
    # bounds the line count, not the bytes).
    truncation = None
    if len(selected) > max_lines or len(selected_text.encode("utf-8")) > max_bytes:
        truncation = truncate_tail(selected_text, max_lines=max_lines, max_bytes=max_bytes)
        return {
            "content": truncation.content,
            "truncation": truncation,
        }
    return {"content": selected_text, "truncation": None}


def read_image_file(file_path: str) -> dict:
    """Read an image file + return base64-encoded
    data. Mirrors the image-read path of
    the OpenClaw source's ``read.ts`` execute
    function.

    Returns ``{"data": str, "mimeType": str}``.
    """
    resolved = resolve_unicode_path(file_path)
    if not os.path.exists(resolved):
        raise FileNotFoundError(f"File not found: {resolved}")
    if os.path.isdir(resolved):
        raise IsADirectoryError(
            f"Read requires a file path, but '{resolved}' is a directory. "
            "Use 'ls' to list its contents, then read a specific file."
        )
    raw = Path(resolved).read_bytes()
    mime = detect_image_mime_type(resolved)
    if mime is None:
        raise ValueError(f"Not an image file (cannot detect MIME type): {resolved}")
    return {
        "data": base64.b64encode(raw).decode("ascii"),
        "mimeType": mime,
    }


# ============================================================================
# Read tool factory
# ============================================================================


def create_read_tool_definition(
    cwd: str = "",
    options: Optional[dict] = None,
) -> ToolDefinition:
    """Build the :class:`ToolDefinition` for
    the read tool. Mirrors
    ``createReadToolDefinition`` (``read.ts:329``).
    """

    async def _execute(
        tool_call_id: str,
        params: dict,
        signal: object = None,
        on_update: object = None,
        ctx: object = None,
    ) -> AgentToolResult:
        if signal is not None and getattr(signal, "is_set", lambda: False)():
            raise RuntimeError("Operation aborted")
        path = params.get("path", "")
        offset = params.get("offset")
        limit = params.get("limit")
        if not path:
            raise ValueError("path is required")
        # Resolve the path (with Unicode, slash hygiene, and variants)
        resolved = resolve_unicode_path(path, cwd)

        # Apply sandbox and tool policy security floor
        from ...sandbox import guard_sandbox_tool_access

        _, validated = guard_sandbox_tool_access(
            "read", resolved, cwd, options, ctx, is_mutation=False
        )
        if validated is not None:
            resolved = str(validated)

        # Check if resolved is a directory before attempting file operations (OpenClaw parity)
        if os.path.isdir(resolved):
            raise IsADirectoryError(
                f"Read requires a file path, but '{resolved}' is a directory. "
                "Use 'ls' to list its contents, then read a specific file."
            )

        try:
            # Check if it's an image
            mime = detect_image_mime_type(resolved)
            if mime is not None and mime in IMAGE_MIME_TYPES:
                image = read_image_file(resolved)
                return {
                    "content": [
                        {
                            "type": "image",
                            "data": image["data"],
                            "mimeType": image["mimeType"],
                        }
                    ],
                    "details": {
                        "kind": "image",
                        "content": image["data"],
                        "mimeType": image["mimeType"],
                    },
                }
            # Text file
            result = read_text_file(resolved, offset=offset, limit=limit)
        except (IsADirectoryError, PermissionError) as err:
            if os.path.isdir(resolved):
                raise IsADirectoryError(
                    f"Read requires a file path, but '{resolved}' is a directory. "
                    "Use 'ls' to list its contents, then read a specific file."
                ) from err
            raise
        if result["truncation"] is not None:
            details = {
                "kind": "truncated",
                "content": result["content"],
                "truncation": {
                    "truncated": result["truncation"].truncated,
                    "truncatedBy": getattr(result["truncation"], "truncated_by", None),
                    "maxLines": getattr(result["truncation"], "max_lines", None),
                    "maxBytes": getattr(result["truncation"], "max_bytes", None),
                },
            }
        else:
            details = {
                "kind": "text",
                "content": result["content"],
            }
        return {"content": [{"type": "text", "text": result["content"]}], "details": details}

    return {
        "name": "read",
        "label": "read",
        "description": (
            f"Read a text or image file. Text caps {DEFAULT_MAX_LINES} lines "
            f"or {DEFAULT_MAX_BYTES // 1024}KB. Use offset/limit for large files."
        ),
        "promptSnippet": "Read file contents",
        "promptGuidelines": ["Use read to examine files instead of cat or sed."],
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path to read"},
                "offset": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "1-based line number to start from",
                },
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "Maximum number of lines to read",
                },
            },
            "required": ["path"],
        },
        "outputSchema": {
            "type": "object",
            "properties": {
                "content": {"type": "array"},
                "details": {"type": "object"},
            },
        },
        "execute": _execute,
    }


# Alias for the OpenClaw-shaped factory.
create_read_tool = create_read_tool_definition


__all__ = [
    "IMAGE_MIME_TYPES",
    "create_read_tool",
    "create_read_tool_definition",
    "detect_image_mime_type",
    "read_image_file",
    "read_text_file",
]
