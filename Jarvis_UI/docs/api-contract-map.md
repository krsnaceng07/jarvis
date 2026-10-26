# API & Event Contract Map

**Document Compliance:** PRD Addendum Section 10

| UI Action / State | HTTP Route or WebSocket Event | Request Schema | Response / Event Schema | Auth / Permission | Cancellation Behavior | Test File |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Assistant State Sync** | `assistant.state_changed` | `{}` | `{"state": "listening", "can_cancel": true}` | None (Local Loopback) | Triggers `cancelling` state | `src/tests/stateMachine.test.ts` |
| **User Text Prompt** | `POST /api/v1/chat/messages` | `{"text": string, "session_id": string}` | `{"message_id": string, "status": "sent"}` | Session Token | AbortController on fetch | `src/tests/stores.test.ts` |
| **Stream Chunk Delta** | `assistant.response.delta` | `{}` | `{"chunk": string, "index": number}` | Session Token | Preempted on barge-in | `src/tests/stores.test.ts` |
| **Emergency Terminate** | `POST /api/v1/assistant/sessions/{id}/cancel` | `{"reason": "user_terminate"}` | `{"status": "cancelled", "aborted_tasks": string[]}` | Operator Privilege | Immediate SIGINT / abort | `src/tests/stateMachine.test.ts` |
| **Memory Lookup / Store**| `GET/POST /api/v1/memory` | `{"key": string, "value": string, "category": string}` | `{"id": string, "stored": boolean}` | Local Storage | Transaction rollback on fail | `src/tests/stores.test.ts` |
| **Skill Status Toggle** | `PATCH /api/v1/skills/{id}` | `{"status": "active" \| "standby"}` | `{"id": string, "status": string}` | Local Privilege | None | `src/tests/stores.test.ts` |
| **Visual Task Dispatch** | `POST /api/v1/visual/tasks` | `{"prompt_id": string, "type": string}` | `{"task_id": string, "model_url": string}` | None | Discard render frame | `src/tests/stores.test.ts` |
