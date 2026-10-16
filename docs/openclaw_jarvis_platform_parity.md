# OpenClaw → JARVIS Platform Parity Matrix

Authoritative parity matrix comparing reference OpenClaw (`v2026.9.2`) capabilities against JARVIS (`E:/jarvis`) implementation.

Status Legend:
- `MATCH`: Full architectural, interface, and behavioral parity with source evidence.
- `PARTIAL`: Interface or subsystem exists but lacks specific lifecycle stages or multi-tenant bindings.
- `MISSING`: Capability not yet implemented in JARVIS.
- `INCOMPATIBLE`: Subsystem adapted for Python/Windows/JARVIS architecture.
- `NOT APPLICABLE`: Platform-specific feature (e.g. macOS native menu bar) not applicable to Windows JARVIS.

---

## Parity Matrix (24 Core Platform Capabilities)

| # | Capability | OpenClaw Source Authority | JARVIS Current Implementation | Status | Gap Analysis & Remedy |
| :- | :--- | :--- | :--- | :--- | :--- |
| 1 | Runtime bootstrap | `src/entry.ts`, `src/gateway/server.ts` | `packages/plugin_sdk/loader.py`, `apps/desktop/app.py` | `PARTIAL` | Wire multi-channel supervisor into desktop and CLI entrypoints. |
| 2 | Configuration | `src/config/io.ts`, `src/config/types.openclaw.ts` | `packages/config_core/`, `config/` | `MATCH` | JSON schema enforcement and migrations implemented. |
| 3 | Channel registry | `src/plugins/registry-types.ts:542`, `src/gateway/server-channels.ts` | `packages/plugin_sdk/loader.py:89` | `PARTIAL` | Replace single `channel` slot with `channels: dict[str, ChannelPlugin]`. |
| 4 | Channel lifecycle | `src/gateway/server-channels.ts:700-1050` | `packages/channels_core/router.py` | `PARTIAL` | Implement account lifecycle supervisor (`start_account`, `stop_account`). |
| 5 | Message normalization | `src/channels/turn/run-channel-turn.ts`, `src/plugin-sdk/channel-inbound.ts` | `packages/channels_core/types.py:InboundMessage` | `MATCH` | Inbound and outbound message shapes match OpenClaw contracts. |
| 6 | Routing | `src/channels/chat-meta.ts`, `src/channels/direct-dm.ts` | `packages/channels_core/routing.py`, `router.py` | `MATCH` | Route resolution maps channel targets to session keys. |
| 7 | Session binding | `src/channels/session.ts`, `src/commands/agents_bindings.ts` | `packages/channels_core/bindings.py:BindingRegistry` | `MATCH` | Dynamic subagent and session binding records fully match. |
| 8 | Plugin discovery | `src/plugins/discovery.ts`, `manifest-registry.ts` | `packages/plugin_sdk/loader.py:discover_plugins` | `MATCH` | Scans `extensions/*/openclaw.plugin.json` and verifies manifests. |
| 9 | Plugin loading | `src/plugins/loader.ts`, `src/plugins/api-builder.ts` | `packages/plugin_sdk/loader.py:load_plugins` | `MATCH` | Dynamically loads entries and injects `PluginApi`. |
| 10 | Plugin lifecycle | `src/plugins/api-lifecycle.ts`, `registry-types.ts:468` | `packages/plugin_sdk/plugin_registry_lifecycle.py` | `MATCH` | Status tracking (`loaded`, `disabled`, `error`) and cleanup hooks. |
| 11 | Extension system | `packages/plugin-sdk/`, `extensions/*` | `packages/plugin_sdk/bundle_*.py`, `skills/` | `MATCH` | Supports code plugins, declarative bundles, and skills. |
| 12 | Event bus | `src/hooks/internal-hooks.ts`, `dispatcher.ts` | `packages/plugin_sdk/hook_bus.py`, `src/hooks/` | `MATCH` | Async error-isolated event bus with priorities. |
| 13 | Tool registry | `src/plugins/registry-types.ts:105`, `src/agents/tools/` | `packages/plugin_sdk/_plugin_api_registration_b.py` | `MATCH` | Dynamic tool factory registration with JSON schema. |
| 14 | Provider registry | `src/plugins/registry-types.ts:178`, `src/provider-runtime/` | `packages/plugin_sdk/provider_entry.py`, `speech_provider.py` | `MATCH` | Dedicated registries for LLM, TTS, STT, and embeddings. |
| 15 | Capability discovery | `src/plugins/capability-catalog.ts` | `packages/plugin_sdk/channel_capabilities.py` | `MATCH` | Capability descriptors (`draftPreview`, `actions`, `richBlocks`). |
| 16 | Permissions | `src/infra/exec-approvals.ts`, `exec-safe-bin-policy.ts` | `src/infra/exec_approvals.py`, `exec_policy.py` | `MATCH` | Approval policies and safe binary enforcement. |
| 17 | Execution context | `src/plugins/types.ts:OpenClawPluginToolContext` | `packages/plugin_sdk/context.py:PluginContext` | `PARTIAL` | Enrich tool execution context with runtime turn facts. |
| 18 | State | `src/state/`, `src/plugin-state/` | SQLite store (`~/.jarvis/state/jarvis.sqlite`) | `MATCH` | SQLite-only state storage with sync transactions. |
| 19 | Memory | `extensions/memory-core/`, `extensions/active-memory/` | `extensions/memory_core/runtime.py` | `MATCH` | SQLite FTS5 keyword extraction, pagination, annotations, forgetting. |
| 20 | Self-healing | `src/system-agent/`, `packages/tool-call-repair/` | `src/agents/self_healing/`, `tools.ci` | `MATCH` | Autonomous test diagnosis, repair, and verification. |
| 21 | Health checks | `src/status/`, `src/gateway/server-health.ts` | `packages/plugin_sdk/doctor_contracts.py` | `MATCH` | Status diagnostic collectors and repair hooks. |
| 22 | Logging | `src/logging/subsystem.ts`, `json-console-line.ts` | `packages/logging_core/` | `MATCH` | Structured JSON logging with subsystem loggers. |
| 23 | Shutdown | `src/gateway/server-shutdown.ts` | `packages/plugin_sdk/plugin_registry_lifecycle.py` | `MATCH` | Graceful sidecar shutdown and database drain. |
| 24 | Restart recovery | `src/agents/main-session-recovery/` | `packages/channels_core/bindings.py` | `MATCH` | Session state restored from SQLite without data loss. |
