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
from .compact_reasons import (
    DEFERRED_CONTEXT_ENGINE_COMPACTION_REASON,
    classify_compaction_reason,
    format_unknown_compaction_reason_detail,
    resolve_compaction_failure_reason,
)
from .compact_runtime import compact_embedded_agent_session_direct
from .compact_runtime_types import CompactEmbeddedAgentSessionDirect
from .compact_types import (
    CompactEmbeddedAgentSessionParams,
    CompactEmbeddedAgentSessionRuntimeParams,
    CompactionMessageMetrics,
)
from .compaction_duplicate_user_messages import (
    DEFAULT_DUPLICATE_USER_MESSAGE_WINDOW_MS,
    MIN_DUPLICATE_USER_MESSAGE_CHARS,
    collect_duplicate_user_message_entry_ids_for_compaction,
    dedupe_duplicate_user_messages_for_compaction,
)
from .compaction_harness_model_provider import (
    build_compaction_harness_model_provider,
)
from .compaction_safety_timeout import (
    EMBEDDED_COMPACTION_TIMEOUT_MS,
    compact_context_engine_with_safety_timeout,
    compact_with_safety_timeout,
    resolve_compaction_timeout_ms,
)
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
from .post_compaction_loop_guard import (
    DEFAULT_WINDOW_SIZE as POST_COMPACTION_WINDOW_SIZE,
)
from .post_compaction_loop_guard import (
    PostCompactionLoopPersistedError,
    create_post_compaction_loop_guard,
)
from .run import run_embedded_agent
from .run.execution_context import PreparedEmbeddedRunInput
from .run.internal_params import (
    RunEmbeddedAgentInternalParams,
    RunEmbeddedAgentParamsWithSessionFile,
)
from .run.params import RunEmbeddedAgentParams
from .run_execution import execute_prepared_embedded_run
from .run_loop import run_prepared_embedded_loop
from .run_orchestrator import run_embedded_agent as _run_embedded_agent_orchestrator  # noqa: F401
from .turn_settlement import (
    EmbeddedTurnSettlementRunner,
    TurnSettlementConfig,
    TurnSettlementLoop,
    TurnSettlementResult,
    run_turn_settlement_loop,
)
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
from .runs import (
    EmbeddedAgentQueueMessageOutcome,
    abort_active_embedded_run,
    clear_embedded_agent_run_abortability_for_run_id,
    format_embedded_agent_queue_failure_summary,
    is_embedded_agent_run_abortable_for_run_id,
    is_embedded_run_abandoned,
    mark_active_embedded_run_abandoned,
    queue_embedded_agent_message_with_outcome,
    queue_embedded_agent_message_with_outcome_async,
    register_active_embedded_run,
    retain_embedded_agent_run_abortability_for_run_id,
    unregister_active_embedded_run,
)
from .session_file_key import (
    resolve_embedded_session_file_key,
)
from .thinking_replay_repair import (
    repair_rejected_thinking_replay_in_session_manager,
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
    "execute_prepared_embedded_run",
    "run_prepared_embedded_loop",
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
    # Params
    "RunEmbeddedAgentParams",
    "RunEmbeddedAgentInternalParams",
    "RunEmbeddedAgentParamsWithSessionFile",
    "PreparedEmbeddedRunInput",
    # Helpers
    "build_embedded_message_action_discovery_input",
    "format_embedded_agent_execution_phase",
    "is_runner_abort_error",
    "is_zero_usage_empty_stop_assistant_turn",
    "resolve_embedded_run_failure_signal",
    "resolve_embedded_session_file_key",
    "resolve_failure_signal_code",
    "FAILURE_SIGNAL_CODES",
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
    # Run registry
    "EmbeddedAgentQueueMessageOutcome",
    "abort_active_embedded_run",
    "clear_embedded_agent_run_abortability_for_run_id",
    "format_embedded_agent_queue_failure_summary",
    "is_embedded_agent_run_abortable_for_run_id",
    "is_embedded_run_abandoned",
    "mark_active_embedded_run_abandoned",
    "queue_embedded_agent_message_with_outcome",
    "queue_embedded_agent_message_with_outcome_async",
    "register_active_embedded_run",
    "retain_embedded_agent_run_abortability_for_run_id",
    "unregister_active_embedded_run",
    # Compaction (7.2a)
    "DEFERRED_CONTEXT_ENGINE_COMPACTION_REASON",
    "classify_compaction_reason",
    "format_unknown_compaction_reason_detail",
    "resolve_compaction_failure_reason",
    "compact_embedded_agent_session_direct",
    "CompactEmbeddedAgentSessionDirect",
    "CompactEmbeddedAgentSessionParams",
    "CompactEmbeddedAgentSessionRuntimeParams",
    "CompactionMessageMetrics",
    "DEFAULT_DUPLICATE_USER_MESSAGE_WINDOW_MS",
    "MIN_DUPLICATE_USER_MESSAGE_CHARS",
    "collect_duplicate_user_message_entry_ids_for_compaction",
    "dedupe_duplicate_user_messages_for_compaction",
    "build_compaction_harness_model_provider",
    "EMBEDDED_COMPACTION_TIMEOUT_MS",
    "compact_context_engine_with_safety_timeout",
    "compact_with_safety_timeout",
    "resolve_compaction_timeout_ms",
    "POST_COMPACTION_WINDOW_SIZE",
    "PostCompactionLoopPersistedError",
    "create_post_compaction_loop_guard",
    "repair_rejected_thinking_replay_in_session_manager",
    # Turn Settlement Loop
    "EmbeddedTurnSettlementRunner",
    "TurnSettlementConfig",
    "TurnSettlementLoop",
    "TurnSettlementResult",
    "run_turn_settlement_loop",
]
