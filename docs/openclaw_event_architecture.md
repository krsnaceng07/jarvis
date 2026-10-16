# OpenClaw Event & Hook Architecture

This document details the event bus and lifecycle hook system of OpenClaw (`v2026.9.2`).

---

## 1. Event Bus Philosophy

OpenClaw employs a typed, error-isolated, asynchronous event bus:
- Subscriptions are registered via `api.on(eventName, handler, options)`.
- Handlers run asynchronously with execution timeouts.
- A failure in one hook never disrupts other hooks or the primary agent turn.
- Ordering is deterministic, prioritized by hook priority (`high`, `normal`, `low`).

---

## 2. Standard Lifecycle Hooks

| Hook Name | Trigger Stage | Context Provided | Return Type / Capability |
| :--- | :--- | :--- | :--- |
| `before_prompt_build` | Before agent prompt compilation | `prompt`, `agentId`, `sessionKey`, `trigger` | `{ prependContext?: string }` (Can inject system facts) |
| `before_agent_reply` | Before outbound message send | `replyPayload`, `sessionKey`, `channelId` | Can mutate or suppress outgoing messages |
| `agent_event` | On agent milestone (tool call, status) | `eventType`, `data`, `sessionId` | Observability and live HUD telemetry |
| `subagent_spawn` | When a subagent worker is created | `parentSessionKey`, `subagentId`, `role` | Audit logging and quota tracking |
| `turn_start` | At turn inception | `turnId`, `senderId`, `inboundMessage` | Metric initialization |
| `turn_end` | After outbound delivery | `turnId`, `durationMs`, `tokenUsage` | Cost accounting and history persistence |
| `tool_call_start` | Prior to tool execution | `toolName`, `params`, `callId` | Security auditing and policy checks |
| `tool_call_end` | Following tool execution | `toolName`, `result`, `durationMs` | Execution verification and self-healing |

---

## 3. Hook Error Isolation & Execution Contract

```text
Hook Dispatcher
       │
       ├─► Sort handlers by [Priority, Registration Order]
       │
       ├─► For each handler:
       │     ┌────────────────────────────────────────────────────────┐
       │     │ try:                                                   │
       │     │     await handler(event, context)                      │
       │     │ except Exception as err:                               │
       │     │     logger.warn(f"Hook {name} failed: {err}")          │
       │     │     # Continue executing remaining handlers            │
       │     └────────────────────────────────────────────────────────┘
       │
       └─► Return aggregated outcomes
```
