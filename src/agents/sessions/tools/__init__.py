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

from typing import Optional

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
# Port note: the rewrite of edit_diff.ts (planned for the
# brain-audit Step 1) isn't on HEAD yet — the current
# edit_diff.py is the pre-rewrite 18486-B version that
# still exposes the legacy surface (``Edit``,
# ``EditNoChangeError``, ``apply_edits``,
# ``create_unified_patch``). The barrel imports the new
# names so the rewrite is a drop-in: until the rewrite
# lands, fall back to ``None`` for the symbols that
# don't exist on the legacy file. Anything that actually
# depends on those names is broken today anyway.
from .edit_diff import (  # noqa: F401
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

try:
    from .edit_diff import (  # type: ignore[attr-defined]
        EDIT_CANDIDATE_LIMIT,
        EDIT_CANDIDATE_MAX_LINES,
        EDIT_CANDIDATE_MAX_SCAN_CHARS,
        EDIT_CANDIDATE_MAX_LINE_CHARS,
        EDIT_CANDIDATE_MIN_SCORE,
        EditDiffError,
        EditDiffResult,
        apply_edits_to_normalized_content,
        compute_edits_diff,
        generate_diff_string,
        generate_unified_patch,
        split_no_op_edits,
        validate_no_op_edit_targets,
    )
except ImportError:
    EDIT_CANDIDATE_LIMIT = 0  # type: ignore[assignment]
    EDIT_CANDIDATE_MAX_LINES = 0  # type: ignore[assignment]
    EDIT_CANDIDATE_MAX_SCAN_CHARS = 0  # type: ignore[assignment]
    EDIT_CANDIDATE_MAX_LINE_CHARS = 0  # type: ignore[assignment]
    EDIT_CANDIDATE_MIN_SCORE = 0  # type: ignore[assignment]
    EditDiffError = None  # type: ignore[assignment]
    EditDiffResult = None  # type: ignore[assignment]
    apply_edits_to_normalized_content = None  # type: ignore[assignment]
    compute_edits_diff = None  # type: ignore[assignment]
    generate_diff_string = None  # type: ignore[assignment]
    generate_unified_patch = None  # type: ignore[assignment]
    split_no_op_edits = None  # type: ignore[assignment]
    validate_no_op_edit_targets = None  # type: ignore[assignment]
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
    EDIT_MISMATCH_HINT_LIMIT,
    EDIT_MISMATCH_MESSAGE,
    EditOperations,
    EditResult,
    EditToolOptions,
    append_mismatch_hint,
    create_edit_tool,
    create_edit_tool_definition,
    default_edit_operations,
    did_edit_likely_apply,
    edit_file,
    prepare_edit_arguments,
    remove_exact_occurrences,
    validate_edit_input,
)
from .apply_patch import (
    create_apply_patch_tool,
    create_apply_patch_tool_definition,
)
from .ls import (
    create_ls_tool,
    create_ls_tool_definition,
)
from .ask_user import (
    create_ask_user_tool,
    create_ask_user_tool_definition,
)
from .message_tool import (
    create_message_tool,
    create_message_tool_definition,
)
from .screen_tool import (
    create_screen_tool,
    create_screen_tool_definition,
)
from src.canvas.widget_tool import (
    create_show_widget_tool,
)

# Phase 6.10d — search + bash
from .bash_operations import (
    BashExecOptions,
    BashOperations,
    OnData,
)
from .bash import (
    DEFAULT_BASH_TIMEOUT_MS,
    create_bash_tool,
    create_bash_tool_definition,
    create_local_bash_operations,
    execute_bash,
    resolve_bash_timeout_ms,
)

from .exec_tool import create_exec_tool
from .process_tool import create_process_tool
from .mkdir_tool import create_mkdir_tool, create_mkdir_tool_definition
from .remove_path_tool import create_remove_path_tool, create_remove_path_tool_definition
from .rename_path_tool import create_rename_path_tool, create_rename_path_tool_definition
from .open_path_tool import create_open_path_tool, create_open_path_tool_definition
from .skill_workshop_tool import create_skill_workshop_tool, create_skill_workshop_tool_definition
from .audio_tool import create_audio_tool, create_audio_tool_definition
from .system_info_tool import create_system_info_tool, create_system_info_tool_definition
from .web_search_tool import create_web_search_tool, create_web_search_tool_definition
from .web_fetch_tool import create_web_fetch_tool, create_web_fetch_tool_definition
from .automations_tool import create_automations_tool, create_automations_tool_definition
from .pdf_tool import create_pdf_tool, create_pdf_tool_definition
from .secrets_tool import create_secrets_tool, create_secrets_tool_definition
from .channel_tools import (
    CHANNEL_TOOL_DECLARATIONS,
    create_channel_status_definition,
    create_channel_status_tool,
    create_configure_channel_definition,
    create_configure_channel_tool,
)
from .find import (
    DEFAULT_IGNORE_PATTERNS,
    DEFAULT_LIMIT as FIND_DEFAULT_LIMIT,
    FindOperations,
    create_find_tool,
    create_find_tool_definition,
    find_files,
)
from .grep import (
    DEFAULT_CONTEXT,
    DEFAULT_LIMIT as GREP_DEFAULT_LIMIT,
    GrepOperations,
    create_grep_tool,
    create_grep_tool_definition,
    grep_files,
)
from .ls import (
    DEFAULT_LIMIT as LS_DEFAULT_LIMIT,
    LsOperations,
    list_directory,
)
from .session_tools import (
    create_session_status_tool_definition,
    create_sessions_list_tool_definition,
    create_sessions_send_tool_definition,
    create_session_status_tool,
    create_sessions_list_tool,
    create_sessions_send_tool,
)
from .session_management_tools import (
    create_sessions_tool_definition,
    create_sessions_search_tool_definition,
    create_sessions_history_tool_definition,
    create_sessions_tool,
    create_sessions_search_tool,
    create_sessions_history_tool,
)
from .conversation_tools import (
    create_conversations_list_tool_definition,
    create_conversations_send_tool_definition,
    create_conversations_turn_tool_definition,
    create_conversations_list_tool,
    create_conversations_send_tool,
    create_conversations_turn_tool,
)
from .subagent_tools import (
    create_sessions_spawn_tool_definition,
    create_sessions_yield_tool_definition,
    create_subagents_tool_definition,
    create_sessions_spawn_tool,
    create_sessions_yield_tool,
    create_subagents_tool,
)
from .view_image_tool import define_view_image_tool
from .image_generate_tool import define_image_generate_tool
from .video_generate_tool import define_video_generate_tool
from .music_generate_tool import define_music_generate_tool
from .tts_tool import define_tts_tool
from .stt_tool import define_stt_tool


def create_coding_tools(
    cwd: str,
    options: Optional[dict] = None,
) -> list:
    """Create the mutable coding
    tools used by local agent
    sessions (``read`` / ``bash`` /
    ``edit`` / ``write``). Mirrors
    :func:`createCodingTools`
    (``tools/index.ts:203-210``).

    The OpenClaw source returns a
    list of :class:`Tool`
    instances; the Python port
    returns a list of
    :class:`AgentTool` instances
    (the same shape used by the
    agent loop).
    """
    _ = options
    opts = options or {}
    return [
        create_read_tool(cwd, opts),
        create_exec_tool(cwd, opts),
        create_process_tool(cwd, opts),
        create_edit_tool(cwd, opts),
        create_apply_patch_tool(
            cwd, workspace_only=opts.get("workspace_only", False), options=opts
        ),
        create_write_tool(cwd, opts),
        create_mkdir_tool(cwd, opts),
        create_remove_path_tool(cwd, opts),
        create_rename_path_tool(cwd, opts),
        create_open_path_tool(cwd, opts),
        create_audio_tool(opts),
        create_system_info_tool(opts),
        create_web_search_tool(opts),
        create_ls_tool(cwd, options=opts),
        create_message_tool(opts),
        create_ask_user_tool(opts),
        create_screen_tool(opts),
        create_show_widget_tool(
            session_id=opts.get("session_id"),
            agent_id=opts.get("agent_id"),
            state_dir=opts.get("state_dir"),
        ),
        create_sessions_list_tool(),
        create_session_status_tool(),
        create_sessions_send_tool(),
        create_sessions_tool(),
        create_sessions_search_tool(),
        create_sessions_history_tool(),
        create_conversations_list_tool(),
        create_conversations_send_tool(),
        create_conversations_turn_tool(),
        create_sessions_spawn_tool(),
        create_sessions_yield_tool(),
        create_subagents_tool(),
        create_skill_workshop_tool(cwd, opts),
        create_web_fetch_tool(cwd, opts),
        create_automations_tool(cwd, opts),
        create_pdf_tool(cwd, opts),
        create_secrets_tool(cwd, opts),
        define_view_image_tool(),
        define_image_generate_tool(),
        define_video_generate_tool(),
        define_music_generate_tool(),
        define_tts_tool(),
        define_stt_tool(),
    ]


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
    "EditDiffError",
    "EditDiffResult",
    "EditNoChangeError",
    "EditOp",
    "apply_edits_to_normalized_content",
    "compute_edits_diff",
    "count_occurrences",
    "detect_line_ending",
    "fuzzy_find_text",
    "generate_diff_string",
    "generate_unified_patch",
    "levenshtein_distance",
    "normalize_for_fuzzy_match",
    "normalize_to_lf",
    "restore_line_endings",
    "split_no_op_edits",
    "strip_bom",
    "validate_no_op_edit_targets",
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
    "EDIT_MISMATCH_HINT_LIMIT",
    "EDIT_MISMATCH_MESSAGE",
    "EditOperations",
    "EditResult",
    "EditToolOptions",
    "append_mismatch_hint",
    "create_edit_tool",
    "create_edit_tool_definition",
    "default_edit_operations",
    "did_edit_likely_apply",
    "edit_file",
    "prepare_edit_arguments",
    "remove_exact_occurrences",
    "validate_edit_input",
    # Phase 6.10c — apply_patch
    "create_apply_patch_tool",
    "create_apply_patch_tool_definition",
    # Phase 6.10c — ask_user
    "create_ask_user_tool",
    "create_ask_user_tool_definition",
    "create_message_tool",
    "create_message_tool_definition",
    # Phase 6.10c — screen
    "create_screen_tool",
    "create_screen_tool_definition",
    # Phase 6.10d — bash operations
    "BashExecOptions",
    "BashOperations",
    "OnData",
    # Phase 6.10d — bash
    "DEFAULT_BASH_TIMEOUT_MS",
    "create_bash_tool",
    "create_bash_tool_definition",
    "create_local_bash_operations",
    "execute_bash",
    "resolve_bash_timeout_ms",
    # Phase 6.10e — session state tools
    "create_session_status_tool_definition",
    "create_sessions_list_tool_definition",
    "create_sessions_send_tool_definition",
    "create_session_status_tool",
    "create_sessions_list_tool",
    "create_sessions_send_tool",
    # Phase 6.10e — Session Orchestration Tools (Python Parity)
    "create_sessions_tool_definition",
    "create_sessions_search_tool_definition",
    "create_sessions_history_tool_definition",
    "create_sessions_tool",
    "create_sessions_search_tool",
    "create_sessions_history_tool",
    "create_conversations_list_tool_definition",
    "create_conversations_send_tool_definition",
    "create_conversations_turn_tool_definition",
    "create_conversations_list_tool",
    "create_conversations_send_tool",
    "create_conversations_turn_tool",
    "create_sessions_spawn_tool_definition",
    "create_sessions_yield_tool_definition",
    "create_subagents_tool_definition",
    "create_sessions_spawn_tool",
    "create_sessions_yield_tool",
    "create_subagents_tool",
    "define_view_image_tool",
    "define_image_generate_tool",
    "define_video_generate_tool",
    "define_music_generate_tool",
    "define_tts_tool",
    "define_stt_tool",
    # Phase 6.10d — find
    "DEFAULT_IGNORE_PATTERNS",
    "FIND_DEFAULT_LIMIT",
    "FindOperations",
    "create_find_tool",
    "create_find_tool_definition",
    "find_files",
    # Phase 6.10d — grep
    "DEFAULT_CONTEXT",
    "GREP_DEFAULT_LIMIT",
    "GrepOperations",
    "create_grep_tool",
    "create_grep_tool_definition",
    "grep_files",
    # Phase 6.10d — ls
    "LS_DEFAULT_LIMIT",
    "LsOperations",
    "create_ls_tool",
    "create_ls_tool_definition",
    "list_directory",
    # Host control & folder operations
    "create_mkdir_tool",
    "create_mkdir_tool_definition",
    "create_remove_path_tool",
    "create_remove_path_tool_definition",
    "create_rename_path_tool",
    "create_rename_path_tool_definition",
    "create_open_path_tool",
    "create_open_path_tool_definition",
    # Audio, system info, and web search tools
    "create_audio_tool",
    "create_audio_tool_definition",
    "create_system_info_tool",
    "create_system_info_tool_definition",
    "create_web_search_tool",
    "create_web_search_tool_definition",
    # Channel tools
    "CHANNEL_TOOL_DECLARATIONS",
    "create_configure_channel_definition",
    "create_configure_channel_tool",
    "create_channel_status_definition",
    "create_channel_status_tool",
    # Web fetch, automations, pdf, and secrets tools
    "create_web_fetch_tool",
    "create_web_fetch_tool_definition",
    "create_automations_tool",
    "create_automations_tool_definition",
    "create_pdf_tool",
    "create_pdf_tool_definition",
    "create_secrets_tool",
    "create_secrets_tool_definition",
]
