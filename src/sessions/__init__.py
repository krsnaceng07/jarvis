"""JARVIS src/sessions/ — session key + lifecycle surface.

Mirrors OpenClaw's ``src/sessions/``:
- ``classify_session_kind`` — channel / direct / thread / cron / unknown
- ``session_id`` — UUID-shape validation + helpers
- ``session_store`` — in-memory ``SessionStore`` Protocol
- ``session_key_utils`` — parse / canonicalize / fold helpers
- ``session_id_resolution`` — fuzzy session-id resolution
- ``user_turn_media`` — model-facing media-only marker
- ``session_state_event_kinds`` — closed set of state event
  kinds + notify-policy table
- ``session_label`` — user-editable label parser
- ``session_lifecycle_identity`` — identity normalization
- ``session_transcript_runtime`` — transcript target/marker
  types (transcript-events.ts port)
"""
from __future__ import annotations

from .classify_session_kind import classify_session_kind, is_valid_session_kind
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
from .session_id import looks_like_session_id
from .session_label import (
    ParsedSessionLabel,
    SESSION_LABEL_MAX_LENGTH,
    parse_session_label,
)
from .session_lifecycle_events import (
    SessionIdentityMutation,
    SessionIdentityMutationTarget,
    SessionLifecycleEvent,
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
from .session_store import (
    InMemorySessionStore,
    SessionRecord,
    SessionStore,
    get_default_session_store,
    reset_default_session_store,
)
from .user_turn_media import MEDIA_ONLY_USER_TEXT

__all__ = [
    "InMemorySessionStore",
    "MEDIA_ONLY_USER_TEXT",
    "NOTIFY_BY_SESSION_STATE_EVENT_KIND",
    "ParsedSessionLabel",
    "ParsedTraceOverride",
    "ParsedVerboseLabel",
    "ParsedVerboseOverride",
    "SESSION_LABEL_MAX_LENGTH",
    "SessionIdentityMutation",
    "SessionIdentityMutationTarget",
    "SessionLifecycleEvent",
    "SessionRecord",
    "SessionStateActorType",
    "SessionStateEventKind",
    "SessionStore",
    "TraceLevel",
    "VerboseLevel",
    "apply_trace_override",
    "apply_verbose_override",
    "classify_session_kind",
    "decode_session_identity",
    "emit_session_identity_mutation",
    "emit_session_lifecycle_event",
    "get_default_session_store",
    "is_valid_session_kind",
    "looks_like_session_id",
    "normalize_session_identities",
    "normalize_trace_level",
    "normalize_verbose_level",
    "on_session_identity_mutation",
    "on_session_lifecycle_event",
    "parse_session_label",
    "parse_trace_override",
    "parse_verbose_override",
    "reset_default_session_store",
]
