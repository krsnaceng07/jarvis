# OpenClaw Self-Healing & Self-Recovery Architecture

This document defines the architectural blueprint of the Self-Healing and Self-Recovery pipeline inspired by **OpenClaw** and adapted for **JARVIS**.

---

## 1. Architectural Pipeline Map

The self-healing lifecycle follows a strict 9-stage deterministic pipeline:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                       SELF-HEALING LIFECYCLE PIPELINE                       │
└─────────────────────────────────────────────────────────────────────────────┘
  [1] Failure Source
        │ (Network, Model, Tool Execution, Validation, System I/O, Process)
        ▼
  [2] Interception & Detection
        │ (Try/catch blocks, AbortSignal monitors, Exit code checkers)
        ▼
  [3] Event Normalization & Classification
        │ (Produces standardized FailureEvent with ErrorCategory & Signature)
        ▼
  [4] Decision Engine & Budget Gate
        │ (Consults Loop Prevention & History; decides Strategy or Escalate)
        ▼
  [5] Recovery Strategy Selection & Execution
        │ (Backoff, Tool Repair, Model Failover, Context Compaction, Restart)
        ▼
  [6] Environmental Observation
        │ (Captures actual raw output, HTTP responses, OS file/process state)
        ▼
  [7] Execution Verification (Real-World State Check)
        │ (ExecutionVerifier probes real disk, process, network, or data state)
        ▼
  [8] State Ledger & Checkpoint Recording
        │ (Updates LastVerifiedState, logs attempt to RecoveryAuditLedger)
        ▼
  [9] Safe Continuation OR Truthful Escalation
        ├── Success Verified ──> Resume normal agent turn
        └── Recovery Failed  ──> Truthful Escalation (Completed / Failed / Boundary / Next)
```

---

## 2. Core Data Contracts

### 2.1 `ErrorCategory` Enum
Defines closed, domain-rich failure classifications:
- `NETWORK_TRANSIENT`: Connection reset, refused, DNS lookup failure, socket timeout.
- `RATE_LIMIT`: HTTP 429, upstream throttling, `Retry-After` enforcement.
- `AUTH_EXPIRED`: OAuth token expiration, temporary session invalidation.
- `AUTH_PERMANENT`: Invalid API key, forbidden account, unauthorized scope.
- `MODEL_OVERLOADED`: HTTP 503, provider capacity drop, queue full.
- `CONTEXT_OVERFLOW`: Exceeded model token limit or context window.
- `TOOL_VALIDATION_ERROR`: Missing parameter, invalid type, JSON schema mismatch.
- `TOOL_EXECUTION_ERROR`: Command failed, file error, OS permission denied.
- `TOOL_TIMEOUT`: Execution wall-clock exceeded configured threshold.
- `SYSTEM_IO_ERROR`: Disk full, path lock, drive missing.
- `PROCESS_CRASH`: Subprocess exited with non-zero code or killed.
- `INVALID_STATE`: Deserialization error, corrupted transcript, cache invalidation.
- `UNKNOWN`: Unclassified anomaly requiring defensive escalation.

### 2.2 `FailureEvent` Data Structure
```python
@dataclass(frozen=True, slots=True)
class FailureEvent:
    event_id: str
    timestamp: float
    category: ErrorCategory
    severity: Literal["transient", "recoverable", "degraded", "fatal"]
    error_message: str
    exception_type: str
    context: dict[str, Any]  # tool_name, model, params, session_key, etc.
    attempt_count: int
    signature: str  # Hash for loop prevention
```

### 2.3 `RecoveryDecision` & `RecoveryAction`
```python
class RecoveryAction(Enum):
    RETRY_WITH_BACKOFF = "retry_with_backoff"
    REPAIR_ARGUMENTS = "repair_arguments"
    FALLBACK_TOOL = "fallback_tool"
    FALLBACK_PROVIDER = "fallback_provider"
    COMPACT_CONTEXT = "compact_context"
    RESTART_PROCESS = "restart_process"
    ROLLBACK_CHECKPOINT = "rollback_checkpoint"
    ESCALATE_TO_USER = "escalate_to_user"

@dataclass(frozen=True, slots=True)
class RecoveryDecision:
    action: RecoveryAction
    reason: str
    parameters: dict[str, Any]
    backoff_delay_sec: float = 0.0
    fallback_target: str | None = None
    abort_task: bool = False
```

---

## 3. Subsystem State Machines

### 3.1 Model & Provider Failover State Machine
```
[Primary Model Request] ──(HTTP 429/503/Timeout)──> [Failover Retry Controller]
                                                          │
                    ┌─────────────────────────────────────┴────────────────────────┐
                    ▼                                                              ▼
           [Transient Retries]                                            [Budget Exhausted]
       (Exponential Backoff + Jitter)                                              │
                    │                                                              ▼
        ┌───────────┴──────────┐                                      [Select Fallback Model]
        ▼                      ▼                                      (e.g., Gemini -> Groq)
    [Success]              [Failure]                                               │
                               │                                                   ▼
                               └──────────────────────────────────────> [Secondary Model Request]
```

### 3.2 Tool Self-Repair & Recovery State Machine
```
[Tool Call Request] ──> [Schema Validator] ──(Invalid Args)──> [Argument Auto-Repair]
                                                                        │
                                      ┌─────────────────────────────────┴─────────────────┐
                                      ▼                                                   ▼
                              [Repair Succeeded]                                  [Repair Impossible]
                             (Validate Coerced)                                   (Emit Error Result
                                      │                                            to Model for Turn)
                                      ▼
                              [Execute Tool] ──(Command/IO Failure)──> [Tool Failure Classifier]
                                                                                  │
                                      ┌───────────────────────────────────────────┴───────┐
                                      ▼                                                   ▼
                              [Tool Fallback]                                     [Idempotent Retry]
                         (e.g. exec -> powershell)                            (e.g. file lock retry)
```

---

## 4. Anti-Hallucination & Verification Invariants

1. **Pre-Condition & Post-Condition Probing**:
   - For mutating actions (`write`, `edit`, `remove_path`, `exec`), the system must record pre-execution state and physically probe post-execution state.
2. **Never Confuse Attempt With Success**:
   - Emitting a recovery command or invoking a repair function does not constitute a healed state. Only when `ExecutionVerifier.verify()` returns `verified=True` is the recovery ledger marked as successful.
3. **No Hidden Compat or Magic Silencing**:
   - Exceptions are never silently swallowed without recording in `RecoveryAuditLedger`.
4. **Strict Loop Prevention**:
   - Every failure generates a canonical `signature` = `SHA256(category + source + error_snippet + target)`.
   - If the same signature fails 3 times within a single task session, automatic recovery is hard-locked, and execution transitions directly to Truthful Escalation.

---

## 5. Truthful Escalation Contract

When recovery cannot safely proceed or budgets are exhausted, the output format is strictly governed:

```markdown
### ⚠️ Task Execution Boundary Reached

- **Completed:**
  - [List of verified operations that succeeded on the host]
- **Failed step:**
  - [The exact step, tool, or API that failed, along with verified OS error]
- **Retry boundary:**
  - [Explanation of why automatic self-healing halted (e.g., max attempts reached, non-idempotent operation)]
- **Next step:**
  - [Actionable guidance or manual steps for the human operator]
```
