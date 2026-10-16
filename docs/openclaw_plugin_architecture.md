# OpenClaw Plugin Architecture

This document details the plugin platform architecture of OpenClaw (`v2026.9.2`), explaining how extensions register capabilities, manage lifecycle, and isolate errors.

---

## 1. Plugin Manifest (`openclaw.plugin.json`)

Every plugin ships an authoritative manifest file (`openclaw.plugin.json`) at its root directory. This manifest provides machine-readable metadata that the host discovers without executing untrusted code:

```json
{
  "id": "openai",
  "name": "OpenAI Provider",
  "description": "Bundled OpenAI provider plugins for chat, embeddings, and media.",
  "kind": "provider",
  "activation": {
    "onStartup": false
  },
  "providers": ["openai"],
  "channels": [],
  "contracts": {
    "tools": ["image_generate"]
  },
  "configSchema": {
    "type": "object",
    "properties": {
      "apiKey": { "type": "string" }
    }
  },
  "doctorContract": {
    "configRepair": true
  }
}
```

### Manifest Fields
- `id`: Unique kebab-case identifier.
- `name`: Display name.
- `description`: Short explanation of capabilities.
- `kind`: Classification (`channel`, `provider`, `memory`, `tool`, `media`, `voice`, `infrastructure`, `hybrid`).
- `activation`: Defines when the plugin is loaded (`onStartup: true` or `false`).
- `channels`: Array of channel IDs owned by this plugin.
- `providers`: Array of model provider IDs registered by this plugin.
- `contracts`: Declares static guarantees (e.g. tools exported, services provided).
- `configSchema`: JSON Schema validating user settings in `config.json`.
- `doctorContract`: Hooks for automated health checks and config repair (`openclaw doctor --fix`).

---

## 2. Plugin Entrypoint (`definePluginEntry`)

Plugins export a default entry created via `definePluginEntry`:

```typescript
import { definePluginEntry } from "openclaw/plugin-sdk/plugin-entry";

export default definePluginEntry({
  id: "my-plugin",
  name: "My Plugin",
  description: "Custom tools and capabilities",
  kind: "tool",
  register(api) {
    // Register tools, hooks, commands, or providers using api
  },
});
```

---

## 3. The `PluginApi` Interface

The host constructs a dedicated `PluginApi` instance for each plugin during registration. The API exposes structured registration methods:

### 1. Tool Registration
- `api.registerTool(factory, options)`: Registers an agent tool factory. Tool factories receive a rich `OpenClawPluginToolContext` per execution turn (containing `agentId`, `sessionKey`, `channelId`, `senderId`, `sandboxed`).

### 2. Channel Registration
- `api.registerChannel(channelPlugin)`: Registers a messaging channel plugin conforming to `createChatChannelPlugin`.

### 3. Provider Registrations
- `api.registerProvider(provider)`: LLM text inference provider.
- `api.registerEmbeddingProvider(adapter)`: Vector embedding adapter for memory indexers.
- `api.registerSpeechProvider(provider)`: Text-to-speech (TTS) engine.
- `api.registerRealtimeVoiceProvider(provider)`: Full-duplex audio voice provider (WebRTC/LiveKit).
- `api.registerRealtimeTranscriptionProvider(provider)`: Realtime speech-to-text (STT).
- `api.registerImageGenerationProvider(provider)`: Image synthesis engine.
- `api.registerVideoGenerationProvider(provider)`: Video synthesis engine.
- `api.registerMusicGenerationProvider(provider)`: Music and audio synthesis engine.
- `api.registerMediaUnderstandingProvider(provider)`: Multimodal vision/audio analysis.

### 4. Hook & Event Subscriptions
- `api.on(eventName, handler, options)`: Registers lifecycle hooks (`before_prompt_build`, `before_agent_reply`, `agent_event`, etc.) with optional trigger filtering and priority.

### 5. Commands, CLI & Gateway
- `api.registerCommand(commandDecl)`: Registers a user-facing slash command.
- `api.registerCli(registrar, options)`: Extends the `openclaw` CLI with custom subcommands.
- `api.registerHttpRoute(routeDecl)`: Exposes authenticated HTTP endpoints on the gateway.
- `api.registerMemoryCapability(capability)`: Integrates specialized memory search backends.
- `api.lifecycle.registerRuntimeLifecycle(decl)`: Registers cleanup hooks executed on shutdown or disable.

---

## 4. Error Isolation & Fault Tolerance

OpenClaw enforces strict fault isolation between plugins and the host runtime:

1. **Sandboxed Loading**: If importing a plugin or executing `entry.register(api)` throws an error, the error is recorded as a `PluginDiagnostic` in `PluginRegistry.diagnostics`. The failing plugin is marked with `status: "error"` and skipped; the rest of the system continues running without interruption.
2. **Execution Guardrails**: When a plugin tool or hook throws at runtime, the exception is caught, wrapped with a descriptive error result, and returned to the agent loop without crashing the process.
3. **Graceful Teardown**: Each plugin can register cleanup callbacks (`lifecycle.registerRuntimeLifecycle`) to ensure external resources (browser processes, sockets, worker threads) are cleanly terminated when the plugin is reloaded or disabled.
