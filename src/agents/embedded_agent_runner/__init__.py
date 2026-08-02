"""jarvis.agents.embedded_agent_runner — Layer 3 host funnel.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/``.

The embedded-agent runner is the
runtime spine that drives a full
agent run: prompt assembly,
model streaming, tool execution,
compaction, recovery, + terminal
resolution. Layer 2 (``sessions/``)
is the host funnel; Layer 3 is the
loop that runs inside it.

Phase 7.0 — foundational types +
module-level state + small
helpers. The full orchestrator
(``run-orchestrator.ts``), run
loop (``run-loop.ts``), run
registry (``runs.ts``), and the
``run/`` subdir (153 files) land in
7.1+.

The Python port mirrors the OpenClaw
folder structure exactly:
``src/agents/embedded_agent_runner/``
(OpenClaw uses ``embedded-agent-runner/``).

Public surface (re-exported):

- :func:`run_embedded_agent` —
  the public entrypoint.
- :data:`BlockReplyFlushContext` /
  :data:`EmbeddedAgentMeta` /
  :data:`EmbeddedAgentRunMeta` /
  :data:`EmbeddedAgentRunResult` /
  :data:`EmbeddedAgentCompactResult` /
  :data:`EmbeddedSandboxInfo` /
  :data:`EmbeddedRunLivenessState` /
  :data:`EmbeddedRunFailureSignal` /
  :data:`TraceAttempt` /
  :data:`ToolSummaryTrace` —
  the public types.
- :func:`is_runner_abort_error` /
  :func:`is_zero_usage_empty_stop_assistant_turn` /
  :func:`resolve_embedded_run_failure_signal` /
  :func:`resolve_failure_signal_code` /
  :func:`resolve_embedded_session_file_key` /
  :func:`build_embedded_message_action_discovery_input` /
  :func:`format_embedded_agent_execution_phase` —
  small helpers.
"""
from __future__ import annotations

from .abort import is_runner_abort_error
from .empty_assistant_turn import (
    is_zero_usage_empty_stop_assistant_turn,
)
from .execution_phase import (
    EMBEDDED_AGENT_EXECUTION_PHASES,
    EMBEDDED_AGENT_EXECUTION_PHASE_LABELS,
    EmbeddedAgentExecutionPhase,
    format_embedded_agent_execution_phase,
)
from .failure_signal import (
    FAILURE_SIGNAL_CODES,
    resolve_embedded_run_failure_signal,
    resolve_failure_signal_code,
)
from .lanes import (
    CommandLane,
    resolve_embedded_session_lane,
    resolve_global_lane,
    resolve_session_lane,
)
from .logger import log
from .message_action_discovery_input import (
    build_embedded_message_action_discovery_input,
)
from .run import run_embedded_agent
from .run_state import (
    ABANDONED_EMBEDDED_RUNS_BY_SESSION_ID,
    ABANDONED_EMBEDDED_RUN_SESSION_IDS_BY_FILE,
    ABANDONED_EMBEDDED_RUN_SESSION_IDS_BY_KEY,
    ACTIVE_EMBEDDED_RUNS,
    ACTIVE_EMBEDDED_RUNS_BY_RUN_ID,
    ACTIVE_EMBEDDED_RUN_SESSION_IDS_BY_FILE,
    ACTIVE_EMBEDDED_RUN_SESSION_IDS_BY_KEY,
    ACTIVE_EMBEDDED_RUN_SNAPSHOTS,
    AbandonedEmbeddedRun,
    ActiveEmbeddedRunSnapshot,
    EMBEDDED_RUN_WAITERS,
    EmbeddedAgentQueueHandle,
    EmbeddedAgentQueueMessageOptions,
    EmbeddedRunWaiter,
    RETAINED_EMBEDDED_RUN_ABORTABILITY_RUN_IDS,
    get_active_embedded_run_count,
    list_active_embedded_run_session_ids,
    list_active_embedded_run_session_keys,
    resolve_active_embedded_run_session_id,
)
from .session_file_key import (
    resolve_embedded_session_file_key,
)
from .tool_name_allowlist import (
    AGENT_RESERVED_TOOL_NAMES,
    collect_allowed_tool_names,
    collect_core_builtin_tool_names,
    collect_registered_tool_names,
    to_session_tool_allowlist,
)
from .types import (
    BlockReplyFlushContext,
    EmbeddedAgentCompactResult,
    EmbeddedAgentMeta,
    EmbeddedAgentRunMeta,
    EmbeddedAgentRunResult,
    EmbeddedFullAccessBlockedReason,
    EmbeddedRunFailureSignal,
    EmbeddedRunLivenessState,
    EmbeddedSandboxElevated,
    EmbeddedSandboxInfo,
    ToolSummaryTrace,
    TraceAttempt,
)


__all__ = [
    # Public entrypoint
    "run_embedded_agent",
    # Types
    "BlockReplyFlushContext",
    "EmbeddedAgentCompactResult",
    "EmbeddedAgentMeta",
    "EmbeddedAgentRunMeta",
    "EmbeddedAgentRunResult",
    "EmbeddedFullAccessBlockedReason",
    "EmbeddedRunFailureSignal",
    "EmbeddedRunLivenessState",
    "EmbeddedSandboxElevated",
    "EmbeddedSandboxInfo",
    "ToolSummaryTrace",
    "TraceAttempt",
    # Helpers
    "build_embedded_message_action_discovery_input",
    "format_embedded_agent_execution_phase",
    "is_runner_abort_error",
    "is_zero_usage_empty_stop_assistant_turn",
    "resolve_embedded_run_failure_signal",
    "resolve_embedded_session_file_key",
    "resolve_failure_signal_code",
    # Execution phase
    "EMBEDDED_AGENT_EXECUTION_PHASES",
    "EMBEDDED_AGENT_EXECUTION_PHASE_LABELS",
    "EmbeddedAgentExecutionPhase",
    # Lanes
    "CommandLane",
    "resolve_session_lane",
    "resolve_global_lane",
    "resolve_embedded_session_lane",
    # Tool allowlist
    "AGENT_RESERVED_TOOL_NAMES",
    "collect_allowed_tool_names",
    "collect_core_builtin_tool_names",
    "collect_registered_tool_names",
    "to_session_tool_allowlist",
    # Logger
    "log",
    # Run state (Maps)
    "ABANDONED_EMBEDDED_RUNS_BY_SESSION_ID",
    "ABANDONED_EMBEDDED_RUN_SESSION_IDS_BY_FILE",
    "ABANDONED_EMBEDDED_RUN_SESSION_IDS_BY_KEY",
    "ACTIVE_EMBEDDED_RUNS",
    "ACTIVE_EMBEDDED_RUNS_BY_RUN_ID",
    "ACTIVE_EMBEDDED_RUN_SESSION_IDS_BY_FILE",
    "ACTIVE_EMBEDDED_RUN_SESSION_IDS_BY_KEY",
    "ACTIVE_EMBEDDED_RUN_SNAPSHOTS",
    "EMBEDDED_RUN_WAITERS",
    "RETAINED_EMBEDDED_RUN_ABORTABILITY_RUN_IDS",
    "AbandonedEmbeddedRun",
    "ActiveEmbeddedRunSnapshot",
    "EmbeddedAgentQueueHandle",
    "EmbeddedAgentQueueMessageOptions",
    "EmbeddedRunWaiter",
    "get_active_embedded_run_count",
    "list_active_embedded_run_session_ids",
    "list_active_embedded_run_session_keys",
    "resolve_active_embedded_run_session_id",
]
