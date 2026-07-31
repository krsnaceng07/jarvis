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

# Phase 6.10b — output + render + wrapper
from .private_temp_file import (
    create_private_temp_write_stream,
    write_private_temp_file,
)
from .output_accumulator import (
    OutputAccumulator,
    OutputAccumulatorOptions,
    OutputSnapshot,
)
from .render_utils import (
    append_session_tool_truncation_warning,
    format_session_tool_output,
    get_text_output,
    invalid_arg_text,
    normalize_display_text,
    replace_tabs,
    shorten_path,
    str_ as render_str,
)
from .tool_definition_wrapper import (
    AgentTool,
    create_tool_definition_from_agent_tool,
    wrap_tool_definition,
    wrap_tool_definitions,
)

# Phase 6.10c — file ops
from .edit_diff import (
    EDIT_CANDIDATE_LIMIT,
    EDIT_CANDIDATE_MAX_LINES,
    EDIT_CANDIDATE_MAX_SCAN_CHARS,
    EDIT_CANDIDATE_MAX_LINE_CHARS,
    EDIT_CANDIDATE_MIN_SCORE,
    Edit as EditOp,
    EditNoChangeError,
    apply_edits,
    count_occurrences,
    create_unified_patch,
    detect_line_ending,
    fuzzy_find_text,
    levenshtein_distance,
    normalize_for_fuzzy_match,
    normalize_to_lf,
    restore_line_endings,
    strip_bom,
)
from .file_mutation_queue import with_file_mutation_queue
from .read import (
    IMAGE_MIME_TYPES,
    create_read_tool,
    create_read_tool_definition,
    detect_image_mime_type,
    read_image_file,
    read_text_file,
)
from .write import (
    create_write_tool,
    create_write_tool_definition,
    write_file,
)
from .edit import (
    EditResult,
    create_edit_tool,
    create_edit_tool_definition,
    edit_file,
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
    # Phase 6.10b — private temp file
    "create_private_temp_write_stream",
    "write_private_temp_file",
    # Phase 6.10b — output accumulator
    "OutputAccumulator",
    "OutputAccumulatorOptions",
    "OutputSnapshot",
    # Phase 6.10b — render utils
    "append_session_tool_truncation_warning",
    "format_session_tool_output",
    "get_text_output",
    "invalid_arg_text",
    "normalize_display_text",
    "render_str",
    "replace_tabs",
    "shorten_path",
    # Phase 6.10b — tool definition wrapper
    "AgentTool",
    "create_tool_definition_from_agent_tool",
    "wrap_tool_definition",
    "wrap_tool_definitions",
    # Phase 6.10c — edit diff engine
    "EDIT_CANDIDATE_LIMIT",
    "EDIT_CANDIDATE_MAX_LINES",
    "EDIT_CANDIDATE_MAX_SCAN_CHARS",
    "EDIT_CANDIDATE_MAX_LINE_CHARS",
    "EDIT_CANDIDATE_MIN_SCORE",
    "EditNoChangeError",
    "EditOp",
    "apply_edits",
    "count_occurrences",
    "create_unified_patch",
    "detect_line_ending",
    "fuzzy_find_text",
    "levenshtein_distance",
    "normalize_for_fuzzy_match",
    "normalize_to_lf",
    "restore_line_endings",
    "strip_bom",
    # Phase 6.10c — file mutation queue
    "with_file_mutation_queue",
    # Phase 6.10c — read
    "IMAGE_MIME_TYPES",
    "create_read_tool",
    "create_read_tool_definition",
    "detect_image_mime_type",
    "read_image_file",
    "read_text_file",
    # Phase 6.10c — write
    "create_write_tool",
    "create_write_tool_definition",
    "write_file",
    # Phase 6.10c — edit
    "EditResult",
    "create_edit_tool",
    "create_edit_tool_definition",
    "edit_file",
]
