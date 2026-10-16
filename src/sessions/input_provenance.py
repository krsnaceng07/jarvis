"""Backward-compatibility re-exports for jarvis_session_core.input_provenance."""
from __future__ import annotations

from jarvis_session_core.input_provenance import (
    AGENT_MEDIATED_COMPLETION_SOURCE_TOOLS,
    INTER_SESSION_PROMPT_EXPLANATION,
    INTER_SESSION_PROMPT_PREFIX_BASE,
    InputProvenance,
    InputProvenanceKind,
    MAIN_SESSION_RESTART_RECOVERY_SOURCE_TOOL,
    annotate_inter_session_prompt_text,
    apply_input_provenance_to_user_message,
    has_inter_session_user_provenance,
    is_agent_mediated_completion_source_tool,
    is_completion_report_input_provenance,
    is_inter_session_input_provenance,
    is_main_session_restart_recovery_input_provenance,
    normalize_input_provenance,
    should_preserve_user_facing_session_state_for_input_provenance,
    strip_inter_session_prompt_prefix_for_display,
)

__all__ = [
    "AGENT_MEDIATED_COMPLETION_SOURCE_TOOLS",
    "INTER_SESSION_PROMPT_EXPLANATION",
    "INTER_SESSION_PROMPT_PREFIX_BASE",
    "InputProvenance",
    "InputProvenanceKind",
    "MAIN_SESSION_RESTART_RECOVERY_SOURCE_TOOL",
    "annotate_inter_session_prompt_text",
    "apply_input_provenance_to_user_message",
    "has_inter_session_user_provenance",
    "is_agent_mediated_completion_source_tool",
    "is_completion_report_input_provenance",
    "is_inter_session_input_provenance",
    "is_main_session_restart_recovery_input_provenance",
    "normalize_input_provenance",
    "should_preserve_user_facing_session_state_for_input_provenance",
    "strip_inter_session_prompt_prefix_for_display",
]
