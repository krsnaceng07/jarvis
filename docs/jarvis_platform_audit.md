# JARVIS Platform Architecture Audit

This document provides a comprehensive audit of the current JARVIS codebase (`E:/jarvis`) compared against the reference OpenClaw architecture.

---

## 1. Audited Subsystems

### 1. `packages/channels_core`
- **Current Assets**:
  - Typed envelopes: `InboundMessage`, `OutboundMessage`, `ChannelSession`.
  - Routing: `ChannelRouteRef`, `ChannelRouteTarget`, `ChannelRouteThread`, `ConversationRef`.
  - Session Bindings: `SessionBindingRecord`, `BindingRegistry` in `bindings.py`.
  - Security: `AllowlistPolicy` in `allowlist.py`, `PairingManager` in `pairing.py`.
- **Gaps Identified**:
  - Missing the 5-stage turn runner (`run_channel_turn`) orchestrating `ingest -> classify -> preflight -> assemble -> dispatch`.
  - Channel router lacks unified dispatch into agent sessions.

### 2. `packages/plugin_sdk`
- **Current Assets**:
  - `PluginApi`, `PluginContext`, `LoadResult`.
  - Manifest parser and validator (`bundle_manifest.py`, `manifest.py`).
  - Bundle MCP and command loaders (`bundle_mcp.py`, `bundle_commands.py`).
  - Adapters: `channel_adapters.py`, `channel_capabilities.py`, `provider_entry.py`.
- **Gaps Identified**:
  - `loader.py` contains a critical bug: `channel: dict | None = None` ("Single-active channel plugin registration; last writer wins").
  - `PluginRegistry` lacks full structured collections matching OpenClaw's 24 registry fields.

### 3. `apps/desktop`
- **Current Assets**:
  - PyQt6 HUD with Google GenAI Live API WebSocket audio pipeline.
  - Local host tools (screen capture, terminal, processes, audio).
  - Plugin loader integration and hook bus.
- **Gaps Identified**:
  - Inbound messages from channels (Telegram, WhatsApp) do not seamlessly multiplex into the central agent runtime.

### 4. `extensions/`
- **Current Assets**:
  - `telegram`, `whatsapp`, `discord` plugins exist.
  - `memory_core` and `active_memory` are implemented with SQLite FTS5.
  - `google`, `groq`, `elevenlabs`, `fish-audio-speech` providers exist.
- **Gaps Identified**:
  - `extensions/telegram` and `extensions/whatsapp` require wiring to the unified multi-channel supervisor and turn runner.
