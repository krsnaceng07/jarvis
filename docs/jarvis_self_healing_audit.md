# JARVIS Self-Healing & Self-Recovery Audit

This document audits the current state of failure detection, error recovery, verification, and resilience mechanisms across the **JARVIS** codebase (`e:\jarvis`).

---

## 1. Existing Components and Capabilities

JARVIS already possesses foundational resilience primitives scattered across packages and subsystems:

### 1.1 Infrastructure Retry Policy (`src/infra/retry_policy.py`)
- **Implemented**:
  - `retry_async`: Async execution loop with exponential backoff and jitter.
  - Channel retry defaults: Discord (`500ms` base), Telegram (`400ms` base).
  - HTTP `Retry-After` header parser (`parse_retry_after_header_seconds`).
  - Channel error regex matching (`CHANNEL_API_RETRY_REGEX`).
  - SDK retry cap enforcement (`should_inject_x_should_retry_false`).
- **Limitations**:
  - Limited to external HTTP channel APIs.
  - Does not cover agent tools, model streaming, or local filesystem errors.

### 1.2 Execution Verification (`src/agents/verification/execution_verifier.py`)
- **Implemented**:
  - `ExecutionVerifier`: Verifies physical host reality for filesystem and process operations:
    - `verify_filesystem_write`: Verifies file exists and has expected size.
    - `verify_filesystem_path`: Verifies directory/file existence.
    - `verify_filesystem_removal`: Verifies target was deleted.
    - `verify_filesystem_rename`: Verifies old path gone and new path present.
    - `verify_filesystem_edit`: Verifies expected content fragments are present on disk.
    - `verify_process_execution`: Checks exit codes and stdout/stderr markers.
- **Limitations**:
  - Verification currently acts as a passive reporter; it fails the task record, but does not automatically trigger a healing strategy or corrective action.

### 1.3 Tool Loop Detection (`src/agents/tool_loop_detection.py`)
- **Implemented**:
  - Tracks repetitive tool execution signatures across turns.
  - Intervenes on critical loops and blocks execution with an explanatory warning.
- **Limitations**:
  - Focused strictly on loop prevention; does not attempt argument repair or tool substitution.

### 1.4 Desktop Tool Pipeline (`apps/desktop/src/jarvis_desktop/tool_pipeline.py`)
- **Implemented**:
  - Normalizes parameter schemas from uppercase Gemini declarations to JSON Schema.
  - Validates arguments against schemas via `validate_tool_arguments`.
  - Enforces per-tool execution timeouts (`resolve_tool_timeout`).
  - Truncates oversized tool outputs (`truncate_output`).
  - Checks batch parallelizability (`is_batch_parallelizable`).
- **Limitations**:
  - Schema errors are returned directly to the model without automatic heuristic repair.

### 1.5 Embedded Agent Runner Recovery Hooks (`src/agents/embedded_agent_runner/run/attempt_recovery.py`)
- **Implemented**:
  - Hook seams for prompt failure, timeout, and assistant failure recovery.
- **Limitations**:
  - Hooks default to no-op (`asyncio.sleep(0)`); no full recovery coordinator is currently wired to desktop host runs.

---

## 2. Architectural Gaps in JARVIS

| Area | OpenClaw Parity Standard | Current JARVIS Status | Gap Severity |
| :--- | :--- | :--- | :--- |
| **Unified Failure Event** | Standardized `FailureEvent` across all subsystems with categories, severity, and context | Disparate exception catching in individual modules | **High** |
| **Error Taxonomy & Classification** | Domain-rich `ErrorCategory` distinguishing transient network, rate limit, auth, tool error, system I/O | Regex-based check in channels; raw exceptions elsewhere | **High** |
| **Centralized Decision Engine** | `RecoveryDecisionEngine` selecting deterministic strategy based on budget & signature | Ad-hoc error returns | **High** |
| **Autonomous Tool Repair** | Auto-correct common path syntax, Windows backslashes, missing quotes, or parameter aliases | Only basic `oldText`/`old_text` aliasing in desktop app | **Medium** |
| **Tool Fallback Strategy** | If specialized tool fails, fallback to general tool (e.g. `exec` for file ops) | None; tool failure aborts step | **High** |
| **Provider & Model Failover** | Automatic fallback from primary model to secondary (Gemini -> Groq -> Local) on persistent 429/503 | Manual configuration; stream abort kills turn | **High** |
| **Loop-Guarded Recovery** | Bounded attempts per failure signature (max 2-3) to prevent endless repair thrashing | Loop guard detects repetition, but lacks signature tracking for recovery actions | **Medium** |
| **Persistent Audit Ledger** | SQLite-backed recovery audit log tracking attempts, outcomes, and recovery metrics | Ephemeral in-memory logging | **Medium** |
| **Truthful Escalation Format** | Mandatory `Completed / Failed step / Retry boundary / Next step` on unrecoverable failures | Freeform error strings | **High** |

---

## 3. Remediation Roadmap for JARVIS

1. Build `src/agents/self_healing/` as a dedicated core package/subsystem.
2. Implement `FailureEvent`, `ErrorCategory`, and `ErrorClassifier`.
3. Implement `RecoveryDecisionEngine` and strategy executors:
   - `TransientRetryStrategy`
   - `ToolArgumentRepairStrategy`
   - `ToolFallbackStrategy`
   - `ModelFailoverStrategy`
4. Wire `ExecutionVerifier` directly into the self-healing feedback loop.
5. Implement `RecoveryAuditLedger` (additive SQLite table or safe KV store without schema version bump).
6. Implement `TruthfulEscalation` formatter adhering strictly to OpenClaw recovery contracts.
7. Integrate into `apps/desktop/src/jarvis_desktop/app.py` and `packages/agent_runtime/`.
