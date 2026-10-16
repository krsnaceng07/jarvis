# OpenClaw Self-Healing and Recovery System Audit

This document presents a comprehensive architectural and code-level audit of the failure detection, classification, recovery decision-making, and state verification systems in **OpenClaw** (`openclaw/openclaw`).

---

## 1. Executive Summary

OpenClaw implements a multi-tier, defense-in-depth self-healing architecture designed for long-running, autonomous agent workflows. Rather than treating errors as exceptional failures that immediately abort execution, OpenClaw classifies failures along deterministic fault axes, applies bounded recovery strategies, verifies physical state transitions against the real environment, and maintains strict anti-hallucination invariants.

The core invariant governing OpenClaw's resilience is:
> **Execution Intent ≠ Execution Outcome.**  
> An agent model proposing a tool call or an API dispatching a request is merely an intent. Success is only recognized when verified through deterministic observations, state checkpoints, or operating system receipts.

---

## 2. Failure Detection Across Subsystems

OpenClaw detects and intercepts failures at four distinct operational boundaries:

### 2.1 Transport & Network Layer
- **Transient Code Taxonomy**: Located in `packages/ai/src/utils/retryable-network-errors.ts`, OpenClaw enumerates explicit transient error codes:
  - POSIX / Node.js socket errors: `ECONNRESET`, `ECONNREFUSED`, `ENOTFOUND`, `ETIMEDOUT`, `EAI_AGAIN`, `EPIPE`, `EHOSTUNREACH`.
  - HTTP / Fetch codes: `UND_ERR_CONNECT_TIMEOUT`, `UND_ERR_HEADERS_TIMEOUT`, `UND_ERR_SOCKET`, `ERR_STREAM_PREMATURE_CLOSE`.
  - HTTP Status Codes: `408 Request Timeout`, `429 Too Many Requests`, `500 Internal Server Error`, `502 Bad Gateway`, `503 Service Unavailable`, `504 Gateway Timeout`.
- **String & Snippet Matching**: Regex and substring detection for provider error responses (`overloaded`, `rate limit exceeded`, `connection reset by peer`, `socket hang up`, `server temporarily unavailable`).

### 2.2 Model & Provider Failover Layer
- **Failover Taxonomy**: `packages/gateway-protocol/src/failover-reasons.ts` defines 17 standardized failover reasons:
  - `auth`: Temporary authentication token expiration.
  - `auth_permanent`: Invalid API key or disabled account (requires user intervention or key rotation).
  - `format`: Malformed JSON or unparseable streaming chunk.
  - `rate_limit`: Provider rate limit exceeded (HTTP 429).
  - `overloaded`: Provider capacity exceeded (HTTP 503).
  - `billing`: Quota or credit exhaustion.
  - `server_error`: Upstream 5xx HTTP response.
  - `timeout`: Network read/connect timeout.
  - `tls_certificate`: SSL/TLS negotiation error.
  - `context_overflow`: Context window exceeded (prompt + generation tokens > limit).
  - `model_not_found`: Requested model identifier does not exist or has been deprecated.
  - `session_expired`: Upstream session invalidated.
  - `empty_response`: Model returned 0 tokens or empty assistant turn.

### 2.3 Tool Execution & Validation Layer
- **Pre-execution Boundary**: In `packages/agent-core/src/agent-loop.ts`, tool calls are parsed, arguments are prepared via `prepareToolCallArguments`, and validated against JSON schemas via `validateToolArguments`. Schema violations yield immediate `_ImmediateToolCallOutcome` error results containing actionable feedback rather than fatal exceptions.
- **Execution Boundary**: Wrapped in `_executePreparedToolCall` with `AbortSignal` and timeout enforcement. Errors during tool execution are trapped and formatted as `_ExecutedToolCallOutcome(is_error=true)`.
- **Tool Loop Detection**: `packages/agent-core/src/agent-loop.ts` detects critical repetitive tool-calling loops (e.g. repeated identical failed commands). Upon detection, the engine intervenes via `completeToolLoopInterventionBatch`, returning structured guidance to break the loop.

### 2.4 Process & Host Environment Layer
- **Exit Code Inspection**: Subprocesses executed via `exec` track exit codes, `stderr` outputs, and execution duration.
- **Restart Sentinels & Tombstones**: Described in `docs/gateway/restart-recovery.md`, Gateway crashes or unclean shutdowns record restart sentinels. On startup, session locks and orphaned tasks are resolved against the SQLite database using transactional recovery.

---

## 3. Classification and Recovery Decision Ladder

OpenClaw employs a deterministic decision hierarchy to resolve failures without human intervention whenever safe:

```
[ Failure Occurs ]
       │
       ▼
[ Error Classifier ] ──> Is error transient network / rate limit?
       │                    ├── YES ──> [ Exponential Backoff + Jitter ] (up to budget)
       │                    └── NO
       ▼
Is error auth expiration?
       ├── YES ──> [ Profile Rotation / Credential Refresh ]
       └── NO
       ▼
Is error context overflow?
       ├── YES ──> [ Preemptive Compaction / Context Pruning ]
       └── NO
       ▼
Is error model unavailable / overloaded?
       ├── YES ──> [ Model Fallback / Secondary Provider ]
       └── NO
       ▼
Is error tool argument invalid?
       ├── YES ──> [ Schema Feedback to Model / Self-Correction ]
       └── NO
       ▼
Is error tool execution failure?
       ├── YES ──> [ Observe Error, Check Loop Guard, Fallback Tool ]
       └── NO
       ▼
[ Recovery Budget Exhausted or Fatal ]
       │
       ▼
[ Truthful Escalation to User (Completed / Failed / Boundary / Next) ]
```

### 3.1 Retry Supervision (`RetrySupervisor` & `computeBackoff`)
- **Backoff Algorithm**: Full exponential backoff `delay = min_delay * (factor ^ attempt)`, clamped to `max_delay`.
- **Jitter Modes**:
  - `symmetric`: Random fluctuation between `-jitter * delay` and `+jitter * delay`.
  - `positive`: Delay increases by `+random(0, jitter * delay)` to prevent thundering herd problems.
- **Wall-clock Anchors**: Recovery controllers (such as `failover-retry-controller.ts`) enforce an aggregate wall-clock window (typically 90 seconds) across retries so operations do not hang indefinitely.

---

## 4. State Verification & Anti-Hallucination Invariants

OpenClaw strictly enforces the principle of real-world verification:

1. **Transactional Checkpointing**:
   - Session state and transcript entries are committed synchronously to SQLite via Kysely helpers.
   - An interrupted turn or recovering agent resumes from the **last verified checkpoint** rather than re-executing completed side-effects.

2. **Truthful Outcome Reporting Contract**:
   - Defined in `qa/scenarios/personal/failure-recovery.yaml`:
   - When a task experiences a partial failure or unrecoverable error, the agent must report exact facts:
     - `Completed:` Explicitly states which actions actually succeeded and were verified on disk/system.
     - `Failed step:` Identifies the exact failing step and the concrete error message.
     - `Retry boundary:` Explicit statement that the system has halted automatic retries and why.
     - `Next step:` Clear, actionable options for the human operator.
   - Under no circumstances does the system emit premature "all done", "fixed", or synthetic success messages.

---

## 5. Architectural Takeaways for JARVIS

To achieve true parity, JARVIS must replicate:
1. Standardized failure event structures (`FailureEvent`, `ErrorCategory`).
2. Robust error classification covering network, auth, model, tool, and host OS.
3. Multi-tier recovery strategies (transient retry, tool repair, model failover, context compaction).
4. Physical state verification (`ExecutionVerifier`, `LastVerifiedState`).
5. Persistent recovery audit ledger preventing infinite loops.
6. Truthful reporting contract adhering to OpenClaw's recovery formatting.
