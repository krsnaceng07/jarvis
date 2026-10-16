"""jarvis_session_core — session key, lifecycle, and store surface.

OpenClaw parity: mirrors ``src/sessions/``:
- ``classify_session_kind`` — channel / direct / thread / cron / unknown
- ``session_id`` — UUID-shape validation + helpers
- ``session_store`` — in-memory and SQLite-backed ``SessionStore``
- ``session_key_utils`` — parse / canonicalize / fold helpers
- ``session_id_resolution`` — fuzzy session-id resolution
- ``user_turn_media`` — model-facing media-only marker
- ``session_state_event_kinds`` — closed set of state event kinds + notify table
- ``session_label`` — user-editable label parser
- ``session_lifecycle_identity`` — identity normalization
- ``session_transcript_runtime`` / ``transcript_events`` — transcript target/marker types
- ``system_event_queue`` — volatile in-memory queue for session state notices
"""

from __future__ import annotations

from .classify_session_kind import classify_session_kind, is_valid_session_kind
from .input_provenance import (
    AGENT_MEDIATED_COMPLETION_SOURCE_TOOLS,
    INTER_SESSION_PROMPT_EXPLANATION,
    INTER_SESSION_PROMPT_PREFIX_BASE,
    MAIN_SESSION_RESTART_RECOVERY_SOURCE_TOOL,
    InputProvenance,
    InputProvenanceKind,
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
from .level_overrides import (
    ParsedTraceOverride,
    ParsedVerboseOverride,
    TraceLevel,
    VerboseLevel,
    apply_trace_override,
    apply_verbose_override,
    normalize_trace_level,
    normalize_verbose_level,
    parse_trace_override,
    parse_verbose_override,
)
from .session_chat_type import (
    LegacyChatTypeDeriver,
    derive_session_chat_type,
    register_legacy_chat_type_deriver,
)
from .session_chat_type_shared import (
    CanonicalSessionPeerShape,
    SessionKeyChatType,
    derive_session_chat_type_from_key,
    has_ambiguous_canonical_session_peer_shape,
    parse_canonical_session_peer_shape,
)
from .session_id import looks_like_session_id
from .session_id_resolution import (
    SessionEntry,
    SessionIdMatchSelection,
    resolve_preferred_session_key_for_session_id_matches,
    resolve_session_id_match_selection,
)
from .session_key_utils import (
    CasePreservingPeerDescriptor,
    ParsedAgentSessionKey,
    ParsedCronRunScopeSuffix,
    ParsedSessionDeliveryRoute,
    ParsedThreadSessionSuffix,
    RawSessionConversationRef,
    get_subagent_depth,
    is_acp_session_key,
    is_case_preserving_peer,
    is_cron_run_session_key,
    is_cron_session_key,
    is_subagent_session_key,
    normalize_session_key_preserving_opaque_peer_ids,
    normalize_session_peer_id,
    parse_agent_session_key,
    parse_cron_run_scope_suffix,
    parse_raw_session_conversation_ref,
    parse_session_delivery_route,
    parse_thread_session_suffix,
    requires_folded_session_key_alias_proof,
    to_agent_request_session_key,
)
from .session_label import (
    SESSION_LABEL_MAX_LENGTH,
    ParsedSessionLabel,
    parse_session_label,
)
from .session_lifecycle_events import (
    SessionIdentityMutation,
    SessionIdentityMutationListener,
    SessionIdentityMutationTarget,
    SessionLifecycleEvent,
    SessionLifecycleListener,
    emit_session_identity_mutation,
    emit_session_lifecycle_event,
    on_session_identity_mutation,
    on_session_lifecycle_event,
)
from .session_lifecycle_identity import (
    decode_session_identity,
    normalize_session_identities,
)
from .session_state_event_kinds import (
    NOTIFY_BY_SESSION_STATE_EVENT_KIND,
    SessionStateActorType,
    SessionStateEventKind,
)
from .session_state_notices import (
    SESSION_STATE_CONTEXT_PREFIX,
    decode_session_state_notice_context_key,
    encode_notice_target,
    enqueue_session_state_notice,
    is_notifiable_watcher_key,
    session_state_notice_text,
    set_enqueue_system_event,
    set_request_heartbeat,
    should_wake_watcher,
)
from .session_store import (
    SQLITE_SESSIONS_SCHEMA_SQL,
    InMemorySessionStore,
    SessionRecord,
    SessionStore,
    SqliteSessionStore,
    get_default_session_store,
    reset_default_session_store,
)
from .system_event_queue import (
    SystemEventQueue,
    dequeue_system_events,
    enqueue_system_event,
)
from .transcript_events import (
    InternalSessionTranscriptUpdate,
    SessionTranscriptListener,
    SessionTranscriptUpdate,
    SessionTranscriptUpdateTarget,
    emit_session_transcript_update,
    normalize_session_transcript_update,
    on_internal_session_transcript_update,
    on_session_transcript_update,
)
from .user_turn_media import MEDIA_ONLY_USER_TEXT

# Wire the system event queue to the notices module
set_enqueue_system_event(enqueue_system_event)

__all__ = [
    "AGENT_MEDIATED_COMPLETION_SOURCE_TOOLS",
    "CanonicalSessionPeerShape",
    "CasePreservingPeerDescriptor",
    "INTER_SESSION_PROMPT_EXPLANATION",
    "INTER_SESSION_PROMPT_PREFIX_BASE",
    "InMemorySessionStore",
    "InputProvenance",
    "InputProvenanceKind",
    "InternalSessionTranscriptUpdate",
    "LegacyChatTypeDeriver",
    "MAIN_SESSION_RESTART_RECOVERY_SOURCE_TOOL",
    "MEDIA_ONLY_USER_TEXT",
    "NOTIFY_BY_SESSION_STATE_EVENT_KIND",
    "ParsedAgentSessionKey",
    "ParsedCronRunScopeSuffix",
    "ParsedSessionDeliveryRoute",
    "ParsedSessionLabel",
    "ParsedThreadSessionSuffix",
    "ParsedTraceOverride",
    "ParsedVerboseOverride",
    "RawSessionConversationRef",
    "SESSION_LABEL_MAX_LENGTH",
    "SESSION_STATE_CONTEXT_PREFIX",
    "SQLITE_SESSIONS_SCHEMA_SQL",
    "SessionEntry",
    "SessionIdentityMutation",
    "SessionIdentityMutationListener",
    "SessionIdentityMutationTarget",
    "SessionIdMatchSelection",
    "SessionKeyChatType",
    "SessionLifecycleEvent",
    "SessionLifecycleListener",
    "SessionRecord",
    "SessionStateActorType",
    "SessionStateEventKind",
    "SessionStore",
    "SessionTranscriptListener",
    "SessionTranscriptUpdate",
    "SessionTranscriptUpdateTarget",
    "SqliteSessionStore",
    "SystemEventQueue",
    "TraceLevel",
    "VerboseLevel",
    "annotate_inter_session_prompt_text",
    "apply_input_provenance_to_user_message",
    "apply_trace_override",
    "apply_verbose_override",
    "classify_session_kind",
    "decode_session_identity",
    "decode_session_state_notice_context_key",
    "dequeue_system_events",
    "derive_session_chat_type",
    "derive_session_chat_type_from_key",
    "emit_session_identity_mutation",
    "emit_session_lifecycle_event",
    "emit_session_transcript_update",
    "encode_notice_target",
    "enqueue_session_state_notice",
    "enqueue_system_event",
    "get_default_session_store",
    "get_subagent_depth",
    "has_ambiguous_canonical_session_peer_shape",
    "has_inter_session_user_provenance",
    "is_acp_session_key",
    "is_agent_mediated_completion_source_tool",
    "is_case_preserving_peer",
    "is_completion_report_input_provenance",
    "is_cron_run_session_key",
    "is_cron_session_key",
    "is_inter_session_input_provenance",
    "is_main_session_restart_recovery_input_provenance",
    "is_notifiable_watcher_key",
    "is_subagent_session_key",
    "is_valid_session_kind",
    "looks_like_session_id",
    "normalize_input_provenance",
    "normalize_session_identities",
    "normalize_session_key_preserving_opaque_peer_ids",
    "normalize_session_peer_id",
    "normalize_session_transcript_update",
    "normalize_trace_level",
    "normalize_verbose_level",
    "on_internal_session_transcript_update",
    "on_session_identity_mutation",
    "on_session_lifecycle_event",
    "on_session_transcript_update",
    "parse_agent_session_key",
    "parse_canonical_session_peer_shape",
    "parse_cron_run_scope_suffix",
    "parse_raw_session_conversation_ref",
    "parse_session_delivery_route",
    "parse_session_label",
    "parse_thread_session_suffix",
    "parse_trace_override",
    "parse_verbose_override",
    "register_legacy_chat_type_deriver",
    "requires_folded_session_key_alias_proof",
    "reset_default_session_store",
    "resolve_preferred_session_key_for_session_id_matches",
    "resolve_session_id_match_selection",
    "session_state_notice_text",
    "set_enqueue_system_event",
    "set_request_heartbeat",
    "should_preserve_user_facing_session_state_for_input_provenance",
    "should_wake_watcher",
    "strip_inter_session_prompt_prefix_for_display",
    "to_agent_request_session_key",
]
