# OpenClaw vs JARVIS Self-Healing Parity Matrix

This document provides a comprehensive 20-point parity comparison between **OpenClaw** and **JARVIS** self-healing and resilience capabilities.

---

## 20-Point Self-Healing & Recovery Parity Matrix

| # | Capability | OpenClaw Implementation | Current JARVIS Status | Parity Gap | Required Changes in JARVIS |
| :- | :--- | :--- | :--- | :--- | :--- |
| **1** | **Standardized Failure Event Model** | `FailureSignal`, `FailoverReason`, `ExecutedToolCallOutcome` | Ad-hoc exceptions and return values | Missing unified event model | Implement `FailureEvent` dataclass with ID, timestamp, category, severity, context, and signature. |
| **2** | **Domain-Rich Error Taxonomy** | 17 failover reasons + transient codes + tool error codes | Partial channel regex and raw exceptions | Fragmented classification | Implement `ErrorCategory` enum covering Network, Rate Limit, Auth, Model, Tool, IO, and State. |
| **3** | **Transient Network Classification** | `TRANSIENT_NETWORK_CODES` & regex in `retryable-network-errors.ts` | Regex in `src/infra/retry_policy.py` | Limited to channel APIs | Unify in `ErrorClassifier` for all network and HTTP calls. |
| **4** | **Rate Limit & Retry-After Parser** | `parseRetryAfterHeaderSeconds` with date and integer parsing | `parse_retry_after_header_seconds` in `src/infra/retry_policy.py` | Channel only | Connect header parser to global LLM client and tool runners. |
| **5** | **Backoff with Jitter Modes** | `computeBackoff` with `symmetric` and `positive` jitter | `calculate_backoff_delay` in `src/infra/retry_policy.py` | Present, channel-only | Expand jitter support to tool and model retry controllers. |
| **6** | **Wall-Clock Timeout Anchoring** | Wall-clock anchors (e.g. 90s aggregate window) in retry controllers | Per-tool timeout in `tool_pipeline.py` | No aggregate retry window | Add aggregate deadline tracking in `RecoveryDecisionEngine`. |
| **7** | **Model Failover Decision Ladder** | `resolveRunFailoverDecision` across prompt, assistant, and tool stages | Skeleton in `src/agents/embedded_agent_runner/run/failover_policy.py` | Inactive in desktop host | Wire failover decision logic into active agent host loop. |
| **8** | **Model Fallback Chain** | Automatic fallback across configured model profiles | Hardcoded model selection in desktop app | Missing multi-provider chain | Implement `ModelFailoverStrategy` (Gemini -> Groq -> Local). |
| **9** | **Context Overflow Compaction** | `recoverEmbeddedRunOverflow` & preemptive compaction | Implemented in `embedded_agent_runner`, not linked to desktop | Not triggered on token limit in UI | Hook context compaction into desktop error handler. |
| **10** | **Tool Schema Validation & Coercion** | `validateToolArguments` in `packages/agent-core` | `validate_and_coerce` in `tool_pipeline.py` | Fully achieved | Maintain and connect to argument repair strategy. |
| **11** | **Tool Argument Auto-Repair** | `prepareToolCallArguments` auto-fixes path and alias mismatches | Basic `oldText`/`old_text` swap in desktop | Limited heuristics | Implement `ToolArgumentRepairStrategy` (Windows paths, quotes, json decode). |
| **12** | **Tool Fallback Strategy** | Dynamic fallback to shell/script when specialized tool fails | None | Missing | Implement `ToolFallbackStrategy` (e.g. `ls` -> `exec` with `dir`). |
| **13** | **Physical Host Verification** | Kysely state commits & execution receipts | `ExecutionVerifier` in `src/agents/verification` | Present for filesystem, not wired to healing | Connect verifier outcomes directly into recovery decision loop. |
| **14** | **Anti-Hallucination Invariant** | Intent ≠ Success; execution receipts mandatory | Enforced in `app.py` via `ExecutionVerifier` | Present in desktop tools | Preserve and extend to all agent-managed tools. |
| **15** | **Checkpointed State Tracking** | Session transcripts committed before side-effects | `_transcript_store` and task ledger | Partial checkpoint rollback | Implement `LastVerifiedState` tracker for active tasks. |
| **16** | **Tool Loop Intervention** | `completeToolLoopInterventionBatch` in `agent-loop.ts` | `_tool_loop_guard` in `src/agents/tool_loop_detection.py` | Fully achieved | Keep integrated and synchronize with recovery ledger. |
| **17** | **Recovery Loop Prevention** | Max retry budgets and circuit breakers per failure signature | Basic loop count | Missing signature-based limit | Implement `LoopPreventionEngine` with SHA256 failure signatures. |
| **18** | **Persistent Recovery Audit Ledger** | SQLite transaction log for recovery events | Ephemeral print statements | Missing persistent audit log | Implement `RecoveryAuditLedger` (pure additive SQLite table). |
| **19** | **Truthful Escalation Format** | Mandatory `Completed / Failed step / Retry boundary / Next step` | Ad-hoc error strings | Missing structured format | Implement `TruthfulEscalationFormatter`. |
| **20** | **Live Stream Reconnection** | Auto-reconnect with prior session context injection | Reconnect logic in `app.py` | Basic reconnect only | Enhance with exponential backoff and verify stream health. |

---

## Conclusion
JARVIS has the core building blocks for tool execution and verification, but lacks a centralized **Self-Healing & Recovery Subsystem**. Implementing `src/agents/self_healing/` will resolve all identified gaps and achieve full parity with OpenClaw.
