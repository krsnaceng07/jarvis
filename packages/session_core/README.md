# JARVIS Session Core

`jarvis-session-core` provides session key parsing, lifecycle management, store abstractions (`InMemorySessionStore` and `SqliteSessionStore`), transcript event buses, and system event queues following the OpenClaw architecture.

## Components

- **Session Store**: `SessionRecord`, `SessionStore` protocol, `InMemorySessionStore`, `SqliteSessionStore`
- **Key Utilities**: `parse_agent_session_key`, `normalize_session_key_preserving_opaque_peer_ids`, `to_agent_request_session_key`, etc.
- **Classification**: `classify_session_kind`, `derive_session_chat_type`
- **Lifecycle & Identity**: `SessionLifecycleEvent`, `SessionIdentityMutation`, `normalize_session_identities`
- **Notices & Queue**: `enqueue_session_state_notice`, `SystemEventQueue`, `enqueue_system_event`, `dequeue_system_events`
- **Transcript Events**: `emit_session_transcript_update`, `on_session_transcript_update`
