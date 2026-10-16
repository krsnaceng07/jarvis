# OpenClaw End-to-End Runtime Pipeline

This document details the exact, source-backed runtime pipeline of OpenClaw (2026.9.2), from initial discovery to outbound delivery and recovery.

---

## 1. Pipeline Architecture Diagram

`	ext
[PLUGIN DISCOVERY]
       │  Scan extensions/*/openclaw.plugin.json & manifest validation
       ▼
[PLUGIN REGISTRATION]
       │  Execute entry.register(api) into PluginRegistry
       ▼
[GATEWAY SERVER BOOT]
       │  Bind HTTP & WebSocket listeners, initialize kernel state
       ▼
[CHANNEL INITIALIZATION]
       │  Start channel accounts concurrently (startChannelsWithOptions)
       ▼
[INBOUND TRANSPORT EVENT]
       │  Webhook or Polling listener receives raw payload
       ▼
[CHANNEL TURN RUNNER (5 STAGES)]
       │
       ├─► 1. INGEST:     Normalize raw payload into NormalizedTurnInput
       ├─► 2. CLASSIFY:   Determine eventClass (message, reaction, typing, action)
       ├─► 3. PREFLIGHT:  Apply allowlists, mention gating, dedupe, and debouncing
       ├─► 4. ASSEMBLE:   Resolve route, thread context, and sessionKey
       └─► 5. DISPATCH:   Execute agent turn via embedded runner
               │
               ├─► Hook: before_prompt_build (context injection, standing intents)
               ├─► Memory Retrieval: memory_search / memory_get
               ├─► Model Inference: Provider streaming with live draft previews
               ├─► Tool Loop: Approval checks, execution, tool-result middleware
               └─► Outbound Adapter: Message chunking, rich blocks, media, reactions
`

---

## 2. Detailed Pipeline Stages

### Stage 1: Discovery and Registration (src/plugins/)
1. **Manifest Scan**: loader.ts scans all directories under extensions/ and external plugin paths for openclaw.plugin.json.
2. **Schema Validation**: Validates id, kind, channels, providers, contracts, and ctivation.
3. **Module Loading**: Dynamically imports the plugin entrypoint (definePluginEntry).
4. **API Injection**: Passes a scoped PluginApi instance to 
egister(api). The plugin registers tools, channels, providers, hooks, gateway methods, and commands.
5. **Registry Population**: Aggregates all records into the process-wide, immutable PluginRegistry (src/plugins/registry-types.ts).

### Stage 2: Gateway Server Boot (src/gateway/)
1. **Kernel Initialization**: createGatewayKernel prepares memory, auth generation, and database verifiers.
2. **Listener Binding**: Binds HTTP and WebSocket transports (server-ws-runtime.ts). Health check endpoints become immediately available.
3. **Channel Supervisor**: server-channels.ts reads loaded channel plugins and starts all enabled accounts concurrently with bounded concurrency (CHANNEL_STARTUP_CONCURRENCY).
4. **Sidecars & Cron**: Activates scheduled tasks, maintenance routines, and database integrity checks.

### Stage 3: Inbound Transport Ingress (src/channels/)
1. **Transport Listener**: Channel accounts listen via webhooks or long-polling leases (e.g. monitorTelegramProvider or WhatsApp Baileys socket).
2. **Raw Enqueue**: Messages enter the turn queue with connection-dependent rate limiting.

### Stage 4: The 5-Stage Channel Turn Runner (src/channels/turn/run-channel-turn.ts)
1. **Stage 1 — Ingest**: Calls dapter.ingest(raw). Translates platform-specific envelopes into a clean NormalizedTurnInput.
2. **Stage 2 — Classify**: Calls dapter.classify(input). Determines whether the event is an actionable message or an ignored event (e.g. self-echo, bot-loop, delivery ack).
3. **Stage 3 — Preflight**:
   - Matches allowlist policies (llow-from.ts).
   - Checks group mention requirements (mention-gating.ts).
   - Checks duplicate delivery hashes (inbound-dedupe.ts).
   - Applies debounce windows (inbound-debounce-policy.ts).
   - If dropped or handled, records history and halts turn without LLM dispatch.
4. **Stage 4 — Assemble**:
   - Resolves routing targets (chatId, 	hreadId, ccountId).
   - Assembles canonical sessionKey (e.g. 	elegram:default:123456789:topic:42).
   - Evaluates conversation bindings (e.g. bound subagent or specific task).
5. **Stage 5 — Dispatch**: Hands the assembled turn context to the agent execution engine.

### Stage 5: Agent Execution & Retrieval Loop (src/agents/)
1. **Hook Pre-Prompt**: Emits efore_prompt_build. Allows plugins (such as memory-core standing intents) to prepend runtime context.
2. **Context Assembly**: Retrieves recent session messages, relevant project instructions, and system prompts.
3. **Deterministic Memory Recall**: Calls memory_search or memory_get if queries require historical knowledge.
4. **Model Call & Streaming**: Dispatches the prompt to the configured LLM provider.
5. **Live Draft Previews**: While streaming tokens, emits draft preview events to channels supporting progressive text editing (draftPreview capability).
6. **Tool Execution Loop**:
   - Inspects tool call requests.
   - Evaluates security policy, approval rules (exec-approvals.ts), and safe-binary contracts.
   - Executes the tool factory within its isolated context.
   - Invokes gent-tool-result-middleware for output sanitization and error recovery.
   - Re-feeds results to model until a terminal answer is achieved.

### Stage 6: Outbound Delivery & Finalization (src/channels/)
1. **Hook Pre-Reply**: Fires efore_agent_reply hooks.
2. **Payload Normalization**: Sanitizes text, converts markdown formatting to channel-native entities (HTML, MarkdownV2, or plaintext), and attaches media buffers.
3. **Outbound Adapter Delivery**: Calls outbound.send() or outbound.deliver().
4. **Draft Finalization**: Transitions streaming draft messages to finalized messages (inalEdit or 
ormalFallback).
5. **History Recording**: Synchronously writes the completed turn and user/assistant messages to the SQLite session store.

### Stage 7: Error Recovery & Failure Isolation
- **Plugin Crash Isolation**: A throwing plugin during hook or tool execution is caught and logged; it never aborts the gateway or other active sessions.
- **Channel Reconnection**: Network disconnects trigger exponential backoff polling lease renewal (polling-lease.ts).
- **Restart Continuity**: In-flight sessions persist turn state to disk; upon reboot, main-session-restart-recovery.ts recovers orphan runs.
