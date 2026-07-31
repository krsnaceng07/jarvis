"""jarvis.agents.sessions.tools — built-in tool implementations.

OpenClaw parity: mirrors
``openclaw-main/src/agents/sessions/tools/``.

Phase 6.10 — built-in tool surface.

This package ships the seven built-in tools
(``read`` / ``write`` / ``edit`` / ``bash`` /
``find`` / ``grep`` / ``ls``) + the shared
contracts + helpers (tool-contracts,
limits, truncate, path-utils, output-accumulator,
render-utils, tool-definition-wrapper) + the
file-mutation queue + the edit diff engine +
the bash-operations interface.

Sub-phases:
- 6.10a — foundational types + helpers
  (tool_contracts, limits, truncate,
  path_utils)
- 6.10b — output + render + wrapper
  (output_accumulator, render_utils,
  tool_definition_wrapper)
- 6.10c — file ops
  (read, write, edit, edit_diff,
  file_mutation_queue, private_temp_file)
- 6.10d — search + bash
  (find, grep, ls, bash, bash_operations)
"""
from __future__ import annotations

# Phase 6.10a — foundational types + helpers
from .tool_contracts import (
    BashToolDetails,
    BashToolInput,
    EditToolDetails,
    EditToolInput,
    FindToolDetails,
    FindToolInput,
    GrepToolDetails,
    GrepToolInput,
    LsToolDetails,
    LsToolInput,
    ReadToolDetails,
    ReadToolInput,
    ReadToolTruncationDetails,
    TruncationResult,
    WriteToolInput,
    format_full_output_footer,
)
from .limits import (
    SESSION_TOOL_STDERR_TAIL_BYTES,
    append_bounded_text_tail,
    normalize_positive_limit,
)
from .truncate import (
    DEFAULT_MAX_BYTES,
    DEFAULT_MAX_LINES,
    GREP_MAX_LINE_LENGTH,
    format_size,
    truncate_head,
    truncate_line,
    truncate_tail,
)
from .path_utils import (
    resolve_read_path,
    resolve_to_cwd,
)


__all__ = [
    # Phase 6.10a — tool contracts
    "BashToolDetails",
    "BashToolInput",
    "EditToolDetails",
    "EditToolInput",
    "FindToolDetails",
    "FindToolInput",
    "GrepToolDetails",
    "GrepToolInput",
    "LsToolDetails",
    "LsToolInput",
    "ReadToolDetails",
    "ReadToolInput",
    "ReadToolTruncationDetails",
    "TruncationResult",
    "WriteToolInput",
    "format_full_output_footer",
    # Phase 6.10a — limits
    "SESSION_TOOL_STDERR_TAIL_BYTES",
    "append_bounded_text_tail",
    "normalize_positive_limit",
    # Phase 6.10a — truncate
    "DEFAULT_MAX_BYTES",
    "DEFAULT_MAX_LINES",
    "GREP_MAX_LINE_LENGTH",
    "format_size",
    "truncate_head",
    "truncate_line",
    "truncate_tail",
    # Phase 6.10a — path utilities
    "resolve_read_path",
    "resolve_to_cwd",
]
