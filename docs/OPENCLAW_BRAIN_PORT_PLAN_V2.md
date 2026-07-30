# OpenClaw Brain → JARVIS Port Plan (v2)

**Date:** 2026-07-25
**Supersedes:** `docs/OPENCLAW_FULL_BRAIN_PORT_PLAN.md` (2026-07-23) — see §0 for why.
**Reference source:** `openclaw-main/` (snapshot 2026.7.2)
**Goal:** JARVIS's brain becomes OpenClaw's brain — same architecture, structure, workflow, logic, style. The existing Gemini-Live brain is deleted, not kept alongside.
**Governing rules:** `AGENTS.md` (one canonical path, delete the old; core stays plugin-agnostic; plugins cross into core only via `jarvis_sdk.*`; SQLite only; ≤5K changed lines per PR).

---

## 0. Why this document replaces the v1 plan

The v1 plan (`OPENCLAW_FULL_BRAIN_PORT_PLAN.md`) is **not safe to execute as written**. Four of its named port targets do not exist in the OpenClaw snapshot. Verified by direct file check on 2026-07-25:

| v1 sub-phase | Named file | Reality |
|---|---|---|
| v1's 5.6 | `src/agents/turn-executor.ts` | **does not exist** |
| v1's 5.7 | `src/agents/tool-runner.ts` | **does not exist** |
| v1's 5.8 | `src/agents/model-caller.ts` | **does not exist** |
| v1's 5.10 | `src/cli/index.ts` | **does not exist** |

Those three agent files are where v1 located the entire turn/tool/model engine — i.e. the brain itself. The real engine lives in `packages/agent-core/src/`, which v1 does not mention at all. Executing v1 as written means three sub-phases with no source to port from.

Second problem: v1 declares "Next: Phase 5.1 — memory-host-sdk port", but that work is **already done**. All eight `src/memory-host-sdk/*.ts` leaf modules have Python counterparts in `packages/plugin_sdk/src/jarvis_sdk/` (`memory_host_event_store.py`, `_event_export.py`, `_event_types.py`, `_events.py`, `_multimodal.py`, `_query.py`, `_secret.py`, `_status.py` — 34 `memory_host_*` modules in total), and `src/memory/root-memory-files.ts` logic sits in `memory_runtime.py`. Starting there would redo finished work.

Third: v1's LOC estimates for the agent layer are low by roughly an order of magnitude. It budgets ~2-3K LOC for the turn executor; the real core measured below is 5119 LOC plus a ~73K-line runner layer. Estimates that wrong produce plans that stall mid-phase.

**Numbering note (2026-07-25):** the repo has already consumed Phase 5.1–5.6a for the memory-host-sdk and plugin-registry ports (`OPENCLAW_MIGRATION_PLAN.md` §41–§46). The brain phases below therefore start at **5.7**, continuing the existing sequence rather than colliding with it.

This v2 plan keeps v1's Phases 6-10 (cron, channels, providers, cleanup) as still-valid future scope and replaces its Phase 5 entirely.

---

## 1. What OpenClaw's brain actually is

The brain is not one module. It is five layers, and only the innermost is portable in isolation.

### Layer 1 — the loop: `packages/agent-core/src/` (5119 LOC non-test)

This is the real brain. It is a standalone package with no OpenClaw imports; it receives everything through config and dependency injection, which is exactly why it can be ported first and tested headlessly.

| File | LOC | Role |
|---|---|---|
| `agent-loop.ts` | 1130 | the state machine |
| `agent.ts` | 631 | stateful `Agent` wrapper, queues, lifecycle |
| `types.ts` | 547 | every contract |
| `harness/compaction/compaction.ts` | 938 | context-window compaction |
| `harness/compaction/branch-summarization.ts` | 300 | session-tree branch summaries |
| `harness/compaction/utils.ts` | 178 | |
| `harness/utils/truncate.ts` | 388 | |
| `harness/messages.ts` | 200 | `convertToLlm` |
| `harness/types.ts` | 131 | `SessionTreeEntry`, `Result`, `FileOperations` |
| `harness/prompt-template-arguments.ts` | 97 | |
| `harness/env/kill-tree.ts` | 197 | process teardown |
| `harness/session/session.ts` | 85 | `buildSessionContext` |
| `harness/session/uuid.ts` | 55 | `uuidv7` |
| `turn-interruption.ts` | 88 | |
| `runtime-deps.ts` | 45 | DI seam: `{completeSimple, streamSimple}` |
| `reasoning.ts` | 43 | thinking-level → provider mapping |
| `errors.ts` / `index.ts` / `llm.ts` / `validation.ts` | 66 | |

**The loop's shape** (`agent-loop.ts:257` `runLoop`) is a nested state machine, not a `while(true)` over messages:

- Before entering, it drains steering messages once — "user may have typed while waiting" (`agent-loop.ts:271`).
- **Outer loop:** re-enters when follow-up messages arrive after the agent would otherwise have stopped.
- **Inner loop:** one provider request per iteration → `streamAssistantResponse` (`:443`) → `executeToolCalls` (`:546`) → `turn_end` → `shouldStopAfterTurn?` → `prepareNextTurn?` → poll steering → poll follow-up.
- Tool execution has two implementations: `executeToolCallsSequential` (`:619`) and `executeToolCallsParallel` (`:692`). Parallel mode still runs **preflight sequentially**, then executes concurrently, emits `tool_execution_end` in *completion* order, and emits tool-result message artifacts later in *assistant source* order. That ordering distinction is observable behaviour and must be preserved.
- Per-call pipeline: `prepareToolCallArguments` (`:814`) → `resolveToolCallTool` (`:828`) → `prepareToolCall` (`:872`) → `executePreparedToolCall` (`:981`) → `finalizeExecutedToolCall` (`:1040`).
- Abort is not an exception path. `stopIfAborted` (`:270`) synthesises a failure assistant message and emits a *complete, well-formed* event sequence (`turn_start` if needed → `message_start` → `message_end` → `turn_end` → `agent_end`) so downstream session post-processing never compacts from a dangling `toolUse` message.

**The contracts that make this work** (`types.ts`) — these are the part that must be mirrored exactly, because getting them approximately right is what produces subtly wrong behaviour later:

- `StreamFn` **must not throw and must not reject** for request/model/runtime failures. Failures are encoded *in the returned stream* as protocol events plus a final `AssistantMessage` with `stopReason: "error" | "aborted"` and `errorMessage`. Same no-throw contract on `convertToLlm`, `transformContext`, `getApiKey`, `shouldStopAfterTurn`, `getSteeringMessages`, `getFollowUpMessages`. Throwing "interrupts the low-level agent loop without producing a normal event sequence" — i.e. it corrupts the session.
- `AfterToolCallResult` merges **field-by-field with no deep merge**: `content` replaces the whole array, `details` replaces the whole payload, omitted fields keep originals.
- `terminate` triggers early exit **only when every finalized tool result in the batch sets it** (`shouldTerminateToolBatch`, `agent-loop.ts:807`).
- `ToolExecutionMode = "sequential" | "parallel"`, default `"parallel"`. `QueueMode = "all" | "one-at-a-time"`.
- `resolveDeferredTool` returns `undefined` for genuinely unknown names so the loop keeps its normal "Tool `<name>` not found" result; only authorized-but-deferred tools are hydrated.

**Hook wiring reality** (`agent.ts:484` `createLoopConfig`) — verified by reading the function:

- `getSteeringMessages` / `getFollowUpMessages` are **supplied by `Agent` itself** from its internal `steeringQueue` / `followUpQueue` (`agent.ts:515-522`), with a one-shot `skipInitialSteeringPoll` guard. Callers do not pass them; they push via `queueSteer` / `queueFollowUp`.
- `shouldStopAfterTurn` is **never wired anywhere in OpenClaw**. It exists only as a contract (`types.ts:218`) and a consumption site (`agent-loop.ts:407`). Port the parameter; do not invent a producer.
- `prepareNextTurn` is wrapped so `prepareNextTurnWithContext` wins when both are set.

### Layer 2 — the session: `src/agents/sessions/` (3384 LOC in the `AgentSession` family)

The single funnel into the brain is `createAgentSession` (`src/agents/sessions/sdk.ts:277`, 553 LOC) — the only non-test `new Agent(...)` in `src/` (`sdk.ts:444`).

Its build order: cwd/agentDir → `AuthStorage` + `ModelRegistry` → `SettingsManager`/`SessionManager` → `ResourceLoader` → restore prior context via `sessionManager.buildSessionContext()` → resolve model (restore from session, else `findInitialModel`) → resolve and clamp thinking level → compute the tool-name allowlist (the actual `AgentTool[]` is **empty at construction**) → wrap `convertToLlmWithBlockImages` → `new Agent({...})` → restore messages → `new AgentSession({...})`.

System prompt and tools are set **after** construction, on the live instance: `agent.state.tools` / `setActiveToolsByName` and `setBaseSystemPrompt` (`agent-session-base.ts:655-676`). `beforeToolCall` / `afterToolCall` are also installed post-construction by `installAgentToolHooks` (`agent-session-base.ts:215-239`), both delegating to the extension runner's `tool_call` / `tool_result` handlers.

`AgentSession` family: base 825, prompting 545, compaction 431, extensions 420, tree 275, models 246, execution 233, inspection 202, types 123, utils 62, `agent-session.ts` 22 — 3384 total.

Three production callers of `createAgentSession`: `embedded-agent-runner/run/attempt-session.ts:112` (main path), `embedded-agent-runner/compact.ts:1515` (compaction sub-session), `src/worker/embedded-agent.runtime.ts:163`. There is no separate interactive-vs-headless construction — the TUI goes through the same embedded runner.

### Layer 3 — the runner spine: `src/agents/` (1205 files; `embedded-agent-runner/run/` alone is ~73K lines / 152 files)

Full chain from an inbound message to the loop:

gateway (`server-node-events.ts:89`, `server-methods/agent-run-dispatch.ts:154`) or TUI (`tui/embedded-backend.ts:1472`) → `agentCommandFromIngress` (`agents/agent-command.ts:592`) → `agentCommand` (`:519`) → `runEmbeddedAgentAttempt` (`:415`) → `run-embedded-attempt.ts:61` → `runEmbeddedAgent` (`command/attempt-execution.ts:986`) → `runPreparedEmbeddedLoop` (`embedded-agent-runner/run-loop.ts:55`) → `prepareAndDispatchEmbeddedRunAttempt` (`run/attempt-dispatch-preparation.ts:167`) → `dispatchEmbeddedRunAttempt` (`run/run-attempt-dispatch.ts:91`) → `runEmbeddedAttemptWithBackend` (`run/backend.ts:10`) → `runAgentHarnessAttempt` (`harness/selection.ts:449`) → `runAgentHarnessLifecycleAttempt` (`harness/lifecycle.ts:217`) → harness `run` (`harness/builtin-openclaw.ts:8`) → `runEmbeddedAttempt` (`run/attempt.ts:47`) → `prepareEmbeddedAttemptSessionRuntime` (`run/attempt-session-runtime-prepare.ts:111`) → `prepareEmbeddedAttemptAgentSession` (`run/attempt-session.ts:41`) → `createAgentSession`. Turn kicked at `run/attempt-stream-runtime-prepare.ts:141` → `AgentSession.prompt` (`agent-session-prompting.ts:100`) → `Agent.prompt` → `runPromptMessages` (`agent.ts:448`) → `runAgentLoop` (`agent.ts:453`).

`src/agents/harness/` (28 non-test files, 19171 lines incl. tests) is the pluggable-backend seam: `selection.ts` 780, `lifecycle.ts` 298, plus `policy.ts`, `registry.ts`, `tool-surface-bridge.ts`, `tool-result-middleware.ts`, `hook-context.ts`, `context-engine-lifecycle.ts`, `agent-end-side-effects.ts`, `result-classification.ts`, `compaction-recovery.ts`, `native-hook-relay.ts`, `user-input-bridge.ts`.

**This layer is the reason the port must be phased.** It cannot be one PR, and most of it is not needed for a working brain.

### Layer 4 — providers and context: `packages/llm-core/` + `src/llm/` + `src/context-engine/`

`packages/llm-core/src/`: `types.ts` 683 (the wire contracts), `validation.ts` 375, `index.ts` 6. `src/llm/` is only 736 LOC total — a thin facade (`stream.ts` 55, `model-registry.ts` 10, `ai-transport-host.ts` 47, `model-runtime-binding.ts` 32, `oauth.ts` 2). Actual providers live in extensions. This is a small, high-leverage port.

`src/context-engine/` (~2.2K LOC non-test): `registry.ts` 1068, `types.ts` 523, `delegate.ts` 188, `host-compat.ts` 128, `runtime-settings.ts` 123, `quarantine-health.ts` 101, `legacy.ts` 90, `init.ts` 24, `legacy.registration.ts` 11. Pluggable assemble/compact with a legacy-compat proxy and a runtime-quarantine proxy that disables a misbehaving engine.

### Layer 5 — routing and sessions: `src/routing/` (~1.4K LOC non-test) + `src/sessions/` (27 non-test files)

`routing/resolve-route.ts` 823 + `session-key.ts` 326 + 9 smaller files. Tiered binding resolution (exact peer → parent-peer → wildcard → guild+roles → guild → team → account → default) producing an `agentId` + `sessionKey`. `src/sessions/` handles admission control, upstream links, transcript events, session-kind classification.

---

## 2. What JARVIS has today

**The current brain — to be deleted.** `apps/desktop/src/jarvis_desktop/app.py` (815 LOC) holds a single `JarvisLive` class bound to Google Gemini Live's bidirectional audio socket: `LIVE_MODEL = "models/gemini-2.5-flash-native-audio-preview-12-2025"`, `SEND_SAMPLE_RATE = 16000`, `RECEIVE_SAMPLE_RATE = 24000`, `sounddevice` for I/O, API key read from `config/api_keys.json`, system prompt from `core/prompt.txt`, memory injected by `memory_bridge.py` (150 LOC) on a recency basis.

What it structurally lacks, measured against Layer 1: no agent loop (no turn boundary, no steering, no follow-up), no `StreamFn` abstraction (Gemini is hardcoded), no tool-call state machine (the model calls tools through Gemini's own function-calling), no session persistence or session tree, no compaction, no context engine, no provider failover, and **no headless text path** — the brain cannot be exercised without audio hardware, so it cannot be unit-tested at all.

**What is already ported and reusable.** `packages/plugin_sdk/src/jarvis_sdk/` has 80+ modules including the full `memory_host_*` surface (34 modules), `plugin_registry*` (7 modules), `agent_runtime.py` (316 LOC — agent-dir/workspace/model-ref resolution, mirroring `plugin-sdk/agent-runtime`), `routing.py`, `session_transcript_runtime.py`, `result.py`, `retry_runtime.py`, `hook.py`, `cron.py`, `manifest.py`, `context.py`. Six extensions at claimed OpenClaw parity: `memory_core`, `memory_lancedb`, `memory_wiki`, `active_memory`, `cron`, `telegram`. 494 test files.

**Empty or missing.** `src/gateway/` contains only `__init__.py` — the v1 plan's claim of "partial (only server.py basics)" is stale; there is no `server.py`. There is no `packages/agent_runtime/`, no `packages/llm_client/`, no `packages/session_core/`, no `src/context_engine/`, no `src/routing/`, no `src/agents/`. `AGENTS.md` lists 25 planned packages; 1 exists.

---

## 3. Gap analysis — the ordering that matters

The port order is dictated by one question: **what could invalidate everything else?** Answer: the `StreamFn` no-throw contract and the event-sequence completeness guarantee. If the Python provider layer raises exceptions instead of encoding failures in the stream, every downstream layer inherits corrupted sessions, and no amount of later work fixes it. So the provider contract is proved *before* the loop is written, on a stub.

Second ordering constraint: the loop is the only layer with zero OpenClaw imports, so it is the only layer that can be ported and fully tested without first porting anything else. It goes early.

Third: the runner spine (Layer 3, ~73K lines) is mostly transport, recovery, and multi-backend selection. A working brain needs `createAgentSession` and a minimal single-backend attempt path. The rest is deferred past the point where JARVIS is functional.

Fourth, and the reason the old brain cannot be deleted on day one: JARVIS currently has no text-mode brain at all. Deleting `app.py`'s `JarvisLive` before the new loop can hold a conversation leaves the product with no brain. The deletion is therefore its own phase, gated on the new path passing a live smoke test — honouring both the user's "remove the old brain" instruction and `AGENTS.md`'s one-canonical-path rule, without a window where nothing works.

---

## 4. Phased plan

Each phase is one or more PRs under 5K changed lines, and each has a pass/fail check runnable without completing later phases. Phase numbering continues from the completed 4.4.

### Phase 5.7 — LLM contracts and provider facade (prove the no-throw contract first)

**Port:** `packages/llm-core/src/types.ts` (683) + `validation.ts` (375) → `packages/llm_client/src/jarvis_llm/types.py`, `validation.py`. Then `src/llm/stream.ts` (55), `model-registry.ts` (10), `model-runtime-binding.ts` (32), `ai-transport-host.ts` (47) → `jarvis_llm/stream.py`, `model_registry.py`, `runtime_binding.py`, `transport_host.py`.

**Deliverable:** a `StreamFn` protocol and one stub provider that encodes every failure mode in-stream.

**Check (independent):** a test suite that injects timeout, 4xx, 5xx, malformed-payload, and mid-stream abort into the stub and asserts the function never raises and always terminates with an `AssistantMessage` carrying `stop_reason` in `{"error", "aborted"}` plus `error_message`. This is the critical point of the whole port; it gets the deepest verification.

**Est.** ~1.5-2K LOC, 1 PR.

### Phase 5.8 — agent-core: types and harness primitives

**Port:** `agent-core/src/types.ts` (547) → `packages/agent_runtime/src/jarvis_agent/types.py`; `harness/types.ts` (131), `harness/session/uuid.ts` (55), `harness/session/session.ts` (85), `harness/messages.ts` (200), `harness/prompt-template-arguments.ts` (97), `harness/utils/truncate.ts` (388), `runtime-deps.ts` (45), `reasoning.ts` (43), `errors.ts`, `validation.ts`.

**Check:** `uuidv7` monotonicity and timestamp-prefix ordering; `truncate` byte/char boundary cases against the TS test vectors in `truncate.test.ts` (63 lines) ported verbatim; `convert_to_llm` filtering of notification/custom roles against `messages.test.ts` (69 lines).

**Est.** ~1.6K LOC, 1 PR.

### Phase 5.9 — agent-core: the loop

**Port:** `agent-loop.ts` (1130) → `jarvis_agent/agent_loop.py`, preserving function decomposition one-to-one (`run_loop`, `stream_assistant_response`, `execute_tool_calls`, `execute_tool_calls_sequential`, `execute_tool_calls_parallel`, `should_terminate_tool_batch`, `prepare_tool_call_arguments`, `resolve_tool_call_tool`, `prepare_tool_call`, `execute_prepared_tool_call`, `finalize_executed_tool_call`, `emit_tool_execution_end`, `create_tool_result_message`, `emit_tool_result_message`, `create_error_tool_result`, `push_loop_failure`, `stop_if_aborted`). Plus `turn-interruption.ts` (88).

**Check:** port `agent-loop.test.ts` (1847 lines) as the acceptance suite. Specifically assert: parallel mode preflights sequentially but emits `tool_execution_end` in completion order and result messages in source order; `terminate` fires only on unanimous batch consent; abort produces the full five-event sequence; steering drained once before the first turn.

**Est.** ~1.2K LOC implementation + ~1.8K test. Split into 2 PRs (loop, then test suite) to stay under the line limit.

### Phase 5.10 — agent-core: compaction

**Port:** `harness/compaction/compaction.ts` (938), `branch-summarization.ts` (300), `utils.ts` (178) → `jarvis_agent/harness/compaction/`.

**Check:** port `compaction.test.ts` (387), `compaction-image-tokens.test.ts` (106), `compaction-trailing-toolresult.test.ts` (124), `utils.test.ts` (50). Trailing-tool-result and image-token cases are the ones that silently corrupt context if wrong.

**Est.** ~1.4K LOC + ~700 test, 1-2 PRs.

### Phase 5.11 — agent-core: the `Agent` class

**Port:** `agent.ts` (631) → `jarvis_agent/agent.py`, including `create_loop_config`, `run_with_lifecycle`, `run_prompt_messages`, `run_continuation`, the steering/follow-up queues, and `create_context_snapshot`.

**Explicit fidelity notes:** `create_loop_config` supplies steering/follow-up from internal queues, applies the one-shot `skip_initial_steering_poll` guard, and **omits `should_stop_after_turn`** — matching OpenClaw, where no producer exists.

**Check:** `reasoning.test.ts` (68) ported; plus a test asserting a second concurrent `prompt()` raises "Agent is already processing."

**Est.** ~800 LOC, 1 PR. **Milestone: `packages/agent_runtime/` is now a complete standalone brain, testable with a stub provider and no JARVIS integration.**

### Phase 5.12 — context engine

**Port:** `src/context-engine/registry.ts` (1068), `types.ts` (523), `delegate.ts` (188), `host-compat.ts` (128), `runtime-settings.ts` (123), `quarantine-health.ts` (101), `legacy.ts` (90), `init.ts` (24), `legacy.registration.ts` (11) → `src/context_engine/`.

**Check:** register two engines, force one to raise repeatedly, assert the quarantine proxy disables it and the legacy-compat path still assembles a context.

**Est.** ~2.2K LOC, 1-2 PRs.

### Phase 5.13 — routing and session keys

**Port:** `src/routing/resolve-route.ts` (823), `session-key.ts` (326), `binding-scope.ts` (130), `bound-account-read.ts` (143), `channel-route-targets.ts` (100), `bindings.ts` (87), `account-id.ts` (78), `account-lookup.ts` (51), `conversation-ref.ts` (37), `default-account-warnings.ts` (21), `peer-kind-match.ts` (14) → `src/routing/`. Reconcile with the existing `jarvis_sdk/routing.py` — extend it, do not fork it.

**Check:** port `session-key.test.ts` (485) and assert the full tier order (exact peer → parent-peer → wildcard → guild+roles → guild → team → account → default) with a table-driven test.

**Est.** ~1.8K LOC, 1 PR.

### Phase 5.14 — session core and `create_agent_session`

**Port:** `src/agents/sessions/sdk.ts` (553) → `packages/session_core/src/jarvis_session/sdk.py`, plus the `AgentSession` family: `agent-session-base.ts` (825), `-prompting.ts` (545), `-compaction.ts` (431), `-extensions.ts` (420), `-tree.ts` (275), `-models.ts` (246), `-execution.ts` (233), `-inspection.ts` (202), `-types.ts` (123), `-utils.ts` (62). Plus the needed parts of `src/sessions/` (session-key utils, id resolution, lifecycle admission, transcript events).

**Fidelity notes:** tools/system-prompt set post-construction, never in the constructor; `install_agent_tool_hooks` wires `before_tool_call`/`after_tool_call` after construction; `convert_to_llm_with_block_images` wraps the base converter.

**SQLite gate:** session persistence needs a schema. Per `AGENTS.md`, **any schema-version bump requires explicit user approval before implementation** — this phase stops at the schema proposal and waits.

**Check:** create a session, prompt it with a stub provider, restart the process, restore the session, assert the message tree and model selection round-trip.

**Est.** ~3.9K LOC. **3 PRs** (sdk + base; prompting + execution + models; compaction + tree + extensions + inspection).

### Phase 5.15 — minimal runner spine

**Port only what a working brain needs**, not the 73K-line runner: `agents/agent-command.ts` (619), `command/run-embedded-attempt.ts` (631), `embedded-agent-runner/run/attempt.ts` (502), `attempt-session-runtime-prepare.ts` (250), `attempt-session.ts` (199), `attempt-stream-runtime-prepare.ts` (192), `harness/selection.ts` (780), `harness/lifecycle.ts` (298), `harness/builtin-openclaw.ts` (20), `harness/policy.ts`, `harness/registry.ts`, `harness/tool-surface-bridge.ts`, `harness/tool-result-middleware.ts`, `harness/result-classification.ts`, `harness/agent-end-side-effects.ts`, `harness/context-engine-lifecycle.ts`.

**Explicitly deferred:** ACP/MCP bundles, worktrees, sandbox, LSP, multi-backend selection beyond the builtin, compaction-recovery, native-hook-relay, `src/worker/`.

**Check:** headless `jarvis agent run "<prompt>"` completes a multi-turn conversation with two tool calls against a stub provider, and the trajectory JSONL shows the expected event sequence.

**Est.** ~4.5K LOC. **2-3 PRs.**

### Phase 5.16 — gateway

**Port:** `src/gateway/server.ts` (42) + `server.impl.ts` (2431) + the method table and chat-runtime event projection → `src/gateway/`.

**Check:** JSON-RPC round-trip against the method table; a chat request produces the same event projection as the headless path.

**Est.** ~3K LOC, 2 PRs.

### Phase 5.17 — real provider extension (Gemini)

**Port** one provider extension using OpenClaw's provider-runtime shape, so the brain talks to a real model. Gemini first, since the user already has a working key path (note: `OPENCLAW_MIGRATION_PLAN.md` §21 records that the previously committed Gemini/OpenRouter keys are still valid in the wild and **still need rotation by the user**).

**Check:** live `jarvis agent run` against Gemini completes a real multi-turn tool-using conversation. Per §40's lesson learned, this is a live smoke test, not just unit tests.

**Est.** ~800 LOC, 1 PR.

### Phase 5.18 — delete the old brain (irreversible; gated)

**Only after 5.17 passes its live smoke test.** This phase destroys the current working voice path.

**Delete:** `JarvisLive` and the Gemini-Live socket handling in `apps/desktop/src/jarvis_desktop/app.py` (815 LOC), the recency-based `memory_bridge.py` (150 LOC), `core/prompt.txt` as a brain input, and the `config/api_keys.json` read path (credentials move to `~/.jarvis/credentials/` per `AGENTS.md`).

**Rewire:** the desktop UI (`ui.py`, 1706 LOC) becomes a channel/transport in front of the ported brain. Audio in/out stays; the brain behind it is `packages/agent_runtime/`. Text and voice then share one path — which is what makes the brain testable.

**Before executing:** state explicitly what is being destroyed and confirm, per the irreversible-action rule. Tag a rollback point first (the existing `v0.9.0-rc1` on `b3a1e70` is the standing fallback; cut a fresh pre-deletion tag too).

**Check:** desktop voice conversation works end-to-end through the new brain; `grep` confirms zero remaining references to `LIVE_MODEL`, `RECEIVE_SAMPLE_RATE`, and `memory_bridge`.

**Est.** ~2K deletions + ~600 LOC rewire, 1-2 PRs.

### Phase 5.19 — extension migration and verification

Migrate the 6 existing extensions onto the new session/tool surface. Write `docs/OPENCLAW_VERIFICATION_5.md` and update `OPENCLAW_MIGRATION_PLAN.md`.

**Est.** ~1.5K LOC, 1-2 PRs.

---

## 4a. State as of 2026-07-30 — completed real-surface + state-core + 2nd-consumer work

The V2 plan above numbers 5.7-5.19 for the *brain* port. In parallel, a separate stream of work ported the real-surface extension entry points + the `jarvis_state_core` shared connection layer + the sessions 2nd consumers. That work used a parallel 5.17a-5.22 numbering and is now complete. **None of the brain phases above has been touched** by this work — the brain port is still ahead.

### Completed (commits `43fb68a` → `678793d`)

| Phase | Scope | Commit | Tests added |
|---|---|---|---|
| 5.17 | `state_core` base — `StateDatabase` + Kysely-like query + canonical schema | `43fb68a` | 27 |
| 5.17b | `state_core` Phase 1 — lease, readonly, contract, paths, permissions, audit_migration, agent_db | `3741156` | 69 |
| 5.17c | `state_core` Phase 2 — schema_helpers, schema_additive (100+ ensureColumn), schema_repair, operator_approval_migration, session_watch_migration, legacy_backfills, maintenance | `83bf231` | 130 |
| 5.18 | sessions 2nd consumer — `session_state_events` + `session_upstream_links` use `StateDatabase` for connection lifecycle | `ca09358` | 9 |
| 5.19 | real-surface entry points — `logbook` (25K) + `device-pair` (lib/ + plugin.py) | `0706a4e` | 97 |
| 5.20 | sessions 2nd consumer — `SqliteSessionStore` implements `SessionStore` protocol via `StateDatabase` | `58271d4` | 16 |
| 5.21 | real-surface entry points — `acpx` (15K) + `tts-local-cli` (10K) + `llm-task` (14K) | `92404a7` | 103 |
| 5.22 | sessions 2nd consumer — `SqliteSessionTranscriptReader` implements transcript read/cleanup via `StateDatabase` | `678793d` | 37 |
| **Total** | | **8 commits** | **+488 tests** |

**Test count:** 3170 → 3662 (+492 across all 8 phases; +37 from 5.22 alone). 0 regressions. 4 skipped (unchanged — case-insensitive FS + Linux-only tests).

### Pattern established

- **"Second consumer"** — every new module that needs a state DB goes through `jarvis_state_core.StateDatabase` (not its own `connection_factory` pattern). The state_core provides standard pragmas (busy_timeout=5s, WAL, foreign_keys=ON) transparently.
- **"Real surface port"** — for each OpenClaw extension, port the full `register(api)` flow + every SDK registrar the extension calls, not just a stub.
- **Schema bootstrap** — `_schema_ensured` flag + `threading.Lock` for one-shot DDL execution; combined DDL constant + delegate to `state_core.ensure_schema(conn, schema_sql=...)`.
- **Idempotent schema** — `ensure_schema` is lazy and idempotent; first call opens connection + ensures the table exists, subsequent calls no-op.

### What's left for the brain (still ahead)

The V2 plan's Phase 5.7 (LLM contracts + provider facade) onwards has not been started. The completed 5.17-5.22 work above is **infrastructure the brain will consume** (state_core + 2nd consumers + real-surface extensions), not the brain itself.

---

## 4b. State as of 2026-07-30 — Layer 2 port work (Phase 6.0 → 6.3)

The V2 plan covers Layer 1 (the loop, 5.7-5.13) + minimal session core (5.14). In parallel, the Layer 2 host funnel work — what the brain sits on top of — is being ported in a `Phase 6.x` series per [`docs/OPENCLAW_LAYER2_PORT_PLAN.md`](OPENCLAW_LAYER2_PORT_PLAN.md). **The brain port (Layer 1) is still ahead and unchanged** by this work; the 6.x work is the host scaffolding + session codec/IO the brain will eventually call.

### Completed (commits `b3edb0d` → `e04696e`)

| Phase | Scope | Commit | Tests added |
|---|---|---|---|
| 6.0 | Layer 2 scaffolding + helpers + small types (11 modules: defaults, source_info, event_bus, diagnostics, messages, slash_commands, telemetry, auth_guidance, provider_display_names, resolve_config_value) | `b3edb0d` | 41 |
| 6.1 | Layer 2 storage primitives (5 modules: storage_lock, http_dispatcher, exec, bash_executor, keybindings) | `22361cb` | 50 |
| 6.2 | Layer 2 session codec (3 modules: session_manager_id, session_manager_types, session_manager_codec) | `7b909b6` | 65 |
| 6.3 | Layer 2 session IO + discovery (2 modules: session_manager_file, session_manager_list) | `e04696e` | 52 |
| **Total** | | **4 commits** | **+208 tests** |

**Test count:** 3662 → 3870 (+208 across 6.0/6.1/6.2/6.3; +52 from 6.3 alone). 0 regressions across the full suite (4 platform-specific skips unchanged).

### Bug fixes captured this session (Phase 6.0 → 6.3)

- **Phase 6.1 real bugs found + fixed:**
  - `exec.py` `nonlocal output_limit_exceeded` missing in nested `finish()` → `UnboundLocalError`.
  - `exec.py` `time` not imported → `NameError` in monitor thread.
  - `OutputAccumulator.append` returned delta instead of new text → empty buffers.
  - `storage_lock.py` Windows `unlock` not idempotent → `EBADF` on second call.
  - `exec_command` read loop deadlocked without drain threads → rewrote with dedicated stdout/stderr drain threads + abort-signal monitor.
- **Phase 6.2 design choice:** `build_session_context` rewritten to do dict-based projection locally (not calling `jarvis_agent.session_context.build_session_context` because it expects typed `SessionTreeEntry` objects, not dicts).
- **Phase 6.3 design choice:** `json_serialization_can_run_user_code` uses `hasattr(value, "toJSON")` for OpenClaw toJSON detection; empty marker parts raise `ValueError` (not return None) to mirror OpenClaw throw-on-invalid.
- **Phase 6.3 name-collision bug:** `SessionFileSnapshot` was defined in BOTH `session_manager_file` (real dataclass) AND `session_manager_types` (`TypeAlias = Any`). The second import in `__init__.py` shadowed the first, making every test that constructed a snapshot hit `TypeError: Any cannot be instantiated`. Removed the alias.

### What Layer 2 still has (6.4 → 6.14)

- **6.4a**: `session_manager_core.py` (the core class) — **DONE** (`376e404`, 24 tests)
- **6.4b**: `session_manager_persistence.py` (the persistence layer) — **DONE** (`3a5863b`, 12 tests)
- **6.4c**: `session_manager_entries.py` (typed append + getters + branch mutators) — **DONE** (`41dd22b`, 28 tests)
- **6.4d**: `session_manager_branching.py` (the `createBranchedSession` path) — **DONE** (`74bd0e4`, 9 tests)
- **6.5**: session manager facade (`session_manager.py` ~10K)
- **6.6**: auth-storage + oauth-registry (~15K)
- **6.7**: model-registry + resolver (~55K)
- **6.8**: settings-manager (~34K)
- **6.9**: extensions/ (~30K, 5 files: loader, runner, types, wrapper, index)
- **6.10**: tools/ (16 files, ~40K)
- **6.11**: resource-loader + package-manager (~79K)
- **6.12**: AgentSession family (11 files, ~100K) — biggest
- **6.13**: support modules (~25K)
- **6.14**: `createAgentSession` in `sdk.py` (~20K) — the terminal phase

**Phase 6.4 total (a + b + c + d)**: 4 modules + 73 tests (24 + 12 + 28 + 9). Full session-manager class hierarchy (`Core` → `Persistence` → `Entries` → `Branching`) now ported 1:1 from OpenClaw.

**Test count after 6.4**: 3870 → 3943 (+73 across 6.4a/b/c/d). 0 regressions.

After Layer 2 lands, the brain (Layer 1 + Layer 3) + device-pair camelCase fix + desktop rewire remain.

---

## 5. Effort summary

| Phase | Content | LOC (impl + test) | PRs |
|---|---|---|---|
| 5.7 | LLM contracts + provider facade | ~2.0K | 1 |
| 5.8 | agent-core types + harness primitives | ~1.6K | 1 |
| 5.9 | the loop | ~3.0K | 2 |
| 5.10 | compaction | ~2.1K | 1-2 |
| 5.11 | `Agent` class | ~0.8K | 1 |
| 5.12 | context engine | ~2.2K | 1-2 |
| 5.13 | routing | ~1.8K | 1 |
| 5.14 | session core | ~3.9K | 3 |
| 5.15 | minimal runner spine | ~4.5K | 2-3 |
| 5.16 | gateway | ~3.0K | 2 |
| 5.17 | Gemini provider | ~0.8K | 1 |
| 5.18 | delete old brain | ~2.6K | 1-2 |
| 5.19 | migration + verification | ~1.5K | 1-2 |
| **Total** | | **~30K** | **18-23** |

Phases 6-10 from the v1 plan (cron internals, channels framework, remaining ~146 provider/media extensions, final cleanup) remain valid and unchanged as post-brain scope.

---

## 6. Port conventions (carried forward from v1, still correct)

`snake_case` at the function level, `camelCase` preserved at the JSON/data level. `dataclasses.dataclass(frozen=True)` for SDK value types (Pydantic v2 stays deferred). `uv` workspace — every package gets a `pyproject.toml`. Fallible operations return `Result` from `jarvis_sdk.normalization.result`. Agent terminal state normalizes via `packages/agent_runtime/terminal_outcome.py`. SQLite access through SQLAlchemy 2.0 helpers, never raw SQL strings. Extensions import only from `jarvis_sdk.*`. TS type guards (`asPluginId`, `as Record<>`) become explicit `isinstance` checks. TypeBox tool schemas map to Pydantic (deferred to a later phase).

---

## 7. Risks

**Assuming the OpenClaw snapshot at `openclaw-main/` is the intended target** and will not be re-synced mid-port. If it is updated, every LOC figure and line reference in this document goes stale and phases in flight need re-derivation.

**Async/await mismatch is the largest hidden cost.** OpenClaw's loop is natively async with `AbortSignal` propagation through every hook. JARVIS's CLI and tool layer are sync (per the 4.4c/4.4d decision to expose sync wrappers). The loop must be async internally; the sync wrapper boundary is a real design decision at Phase 5.9 and the sync/async seam is where cancellation semantics get silently lost. `asyncio.CancelledError` does not behave like an `AbortSignal` check — the port needs an explicit signal object, not reliance on task cancellation.

**`shouldStopAfterTurn` has no producer in OpenClaw.** Porting it as a parameter is correct; inventing a JARVIS-side producer would violate the architect rule.

**The 73K-line runner layer is deferred, not solved.** Phase 5.15 ports a spine and explicitly skips ACP, MCP, worktrees, sandbox, and multi-backend selection. JARVIS will be behaviourally identical to OpenClaw on the mainline conversational path and will *not* have those capabilities until later phases. If "same to same" is meant to include them, this plan is a subset and the remaining scope is roughly 10-15 further phases.

**Two known pre-existing defects sit under this work**: the 10 documented LLM/cron stubs from Phase 4.4 (`generate_and_append_dream_narrative`, `run_light_dreaming`, `run_rem_dreaming`, `run_dreaming_sweep_phases`, `preview_rem_dreaming`, `seed_historical_daily_memory_signals`, `reconcile_short_term_dreaming_cron_job`, `run_short_term_dreaming_promotion_if_triggered`, `register_short_term_promotion_dreaming`), and 4 test failures at master HEAD from 4.3k's `set_manifest()` requirement. The 4 failures should be fixed before Phase 5.7 so the baseline is green and new failures are attributable.

**Likely: the "100% parity" claims for the 6 existing extensions have not been re-verified in this pass** — they are taken from `OPENCLAW_MIGRATION_PLAN.md`'s own records. Phase 5.19 assumes they migrate cleanly; if parity is weaker than recorded, that phase grows.
