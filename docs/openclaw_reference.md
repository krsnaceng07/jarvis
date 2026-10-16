# OpenClaw Reference Baseline

**OpenClaw Reference Version**: 2026.9.2  
**Schema Versions**: state: 16, gent: 19  
**Reference Source Path**: c:/Users/kcs23/Downloads/openclaw-main (with complete 38,707-file tree synchronized from c:/Users/kcs23/Downloads/openclaw-main (1)/openclaw-main)  
**Package Manager**: pnpm (workspace layout defined in pnpm-workspace.yaml)

---

## 1. Repository Inventory & Structure

OpenClaw is architected as a multi-package, modular, extensible agent gateway platform.

`	ext
openclaw/
├── apps/               # Client applications (macOS, iOS, Android, Linux, Mobile, Swabble)
├── config/             # Base schema and environment configurations
├── docs/               # System documentation and manuals
├── extensions/         # 153 bundled plugins (channels, providers, memory, tools, etc.)
├── packages/           # 23 internal workspace libraries & public contracts
├── src/                # Gateway server runtime, core daemon, CLI, agents, channels, hooks
├── ui/                 # Control UI web dashboard (Vite + Lit / WebAwesome)
└── test/               # Test suites, fixtures, integration harnesses
`

---

## 2. Workspace Packages (packages/)

The 23 packages in packages/ define public contracts, client SDKs, and portable utilities:

| Package | Purpose & Source Role |
| :--- | :--- |
| cp-core | Agent Communication Protocol core definitions and message types. |
| gent-core | Agent turn abstractions, streaming primitives, and prompt structures. |
| i | Core AI client interfaces and common provider types. |
| gateway-client | Client library for communicating with OpenClaw Gateway via WebSocket JSON-RPC. |
| gateway-protocol | Authoritative JSON-RPC protocol schema, method descriptors, and event types. |
| llm-core | Low-level LLM execution abstractions and context formatting. |
| markdown-core | Streaming markdown parser, rich block chunker, and table formatting. |
| media-core | Audio/image/video normalization, MIME detection, rastering, and thumbnailing. |
| media-generation-core | Abstractions for image, video, and music generation providers. |
| media-understanding-common | Audio transcription (STT), speech synthesis (TTS), and multimodal vision helpers. |
| memory-host-sdk | Host interface for memory backends, vector embeddings, and retrieval. |
| mermaid-renderer | Server-side rendering and diagram synthesis for mermaid syntax. |
| model-catalog-core | Model descriptor schema, token limits, pricing, and capability flags. |
| 
et-policy | Network isolation, SSRF prevention, private IP egress blocking, and proxy routing. |
| 
ormalization-core | String, phone number, account ID, and target address sanitization. |
| plugin-package-contract | NPM package metadata, manifest verification, and dependency boundaries. |
| plugin-sdk | Official SDK exposed to extension authors (channel-core, plugin-entry, etc.). |
| 
etry | Backoff policies, circuit breakers, jitter, and retry predicates. |
| sdk | Unified public developer SDK facade. |
| session-url-contract | Session deep-link routing and web-app URL generators. |
| 	erminal-core | PTY / process execution sandbox and terminal streaming protocol. |
| 	ool-call-repair | Self-healing parsing for malformed or truncated model tool calls. |
| workboard-contract | Kanban task board, card lifecycle, and workflow state contracts. |

---

## 3. Core Runtime Subsystems (src/)

The gateway runtime in src/ contains 121 modules organized into clean architectural boundaries:

1. **src/gateway/** (1,432 files):
   - HTTP transport & WebSocket server (server-ws-runtime.ts, server-http-transport.ts).
   - Server kernel, lifecycle state machine, and shutdown drains (server-kernel.ts, server-shutdown.ts).
   - Channel startup and supervisor (server-channels.ts).
   - Active session manager, presence publisher, and connection quotas.

2. **src/channels/** (124 files):
   - Turn execution engine (	urn/run-channel-turn.ts, 	urn/lifecycle.ts, 	urn/execution.ts).
   - Inbound event normalization (inbound-event/context.ts, inbound-event/kind.ts).
   - Allowlist gating, mention detection, and debounce policies (llow-from.ts, mention-gating.ts, inbound-debounce-policy.ts).
   - Channel routing and session key resolution (chat-meta.ts, direct-dm.ts).

3. **src/plugins/** (932 files):
   - Active runtime registry (ctive-runtime-registry.ts, 
egistry-types.ts).
   - Discovery and loader (discovery.ts, loader.ts, manifest-registry.ts).
   - API builder and context injection (pi-builder.ts, ctivation-planner.ts).
   - Hook runners, command dispatchers, and capability registries (hook-runner-global.ts, capability-catalog.ts).

4. **src/agents/**:
   - Embedded agent runner and prompt compilation (embedded-agent-runner/).
   - Tool calling loop, verification, and tool-result middleware.
   - Session compaction and recovery (main-session-recovery/).

5. **src/hooks/**:
   - Internal hook bus and lifecycle dispatchers (internal-hooks.ts, dispatcher.ts).

6. **src/infra/**:
   - Execution approvals (exec-approvals.ts), safe binary policies (exec-safe-bin-policy.ts), network security, and retry policies.

---

## 4. Extension Ecosystem (extensions/)

The extensions/ directory ships 153 bundled extensions classified into:
- **Channels** (27+ platforms): 	elegram, whatsapp, discord, slack, eishu, signal, imessage, googlechat, msteams, matrix, line, irc, etc.
- **Providers** (LLM & Inference): openai, nthropic, google, groq, cerebras, mistral, deepseek, xai, ollama, llm, etc.
- **Memory Backends**: memory-core (markdown + SQLite FTS5), memory-lancedb (vector embeddings), memory-wiki (hierarchical notes).
- **Speech & Audio**: elevenlabs, ish-audio-speech, zure-speech, deepgram, senseaudio.
- **Media Generation**: al, 
unway, pixverse, comfy.
- **Tools & Productivity**: rowser, crabbox, document-extract, irecrawl, onepassword, ault.
