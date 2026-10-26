# Security, Trust Boundaries & Permissions Policy

**Document Compliance:** PRD Section 12 & PRD Addendum Section 11

## 1. Network & Origin Binding
- Local-only loopback binding (`127.0.0.1:7433`). The UI and WebSocket connections never bind to external LAN interfaces by default.
- Cross-Origin Resource Sharing (CORS) restricted to verified local clients.

## 2. Audio & Video Privacy
- Microphone capture requires explicit browser/OS permission grants.
- Visual status indicators pulse whenever audio capture or speech synthesis is active.
- No continuous audio or camera frames are cached or persisted to disk without operator request.

## 3. High-Impact Action Confirmation
- Destructive operations (database truncation, file removal, external network dispatch) trigger `waiting_for_permission` state.
- `TERMINATE` button provides immediate fail-safe abort.
