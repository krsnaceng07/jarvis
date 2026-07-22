# JARVIS extensions

The plugin ecosystem. Each extension ships a `jarvis.plugin.json` manifest and
lives in its own subdirectory. Extensions import **only from `jarvis_sdk`** (the
plugin SDK in `packages/plugin_sdk/`).

Mirrors OpenClaw's `extensions/` (152 extensions broken into channels, providers,
media, memory, tools, productivity, voice, infrastructure, migration).

## Layout

| Category | Count target | Examples |
|---|---|---|
| **Channels** (messaging surfaces) | 8 | telegram, discord, slack, whatsapp, signal, matrix, feishu, msteams |
| **Providers** (LLM/model providers) | 10 | openai, anthropic, google, openrouter, ollama, minimax, mistral, xai, copilot, openai_codex |
| **Media** (image/video/music/TTS/STT) | 8 | image_generation, video_generation, music_generation, tts_elevenlabs, tts_local, stt_whisper, stt_openai, media_understanding |
| **Memory** (single active slot) | 3 | memory_core, memory_lancedb, memory_wiki |
| **Tools** (action modules — all are OpenClaw-parity; JARVIS-original tools removed Phase 4.3h) | 0 | _(none yet; OpenClaw has no general-purpose tool extensions beyond channels/providers/memory)_ |
| **Productivity** (personal integrations) | 7 | obsidian, notion, github, calendar, tasks, reminders_macos, notes_macos |
| **Voice / talk** | 3 | talk_voice, voice_wake, voice_call |
| **Infrastructure / ops** | 5 | webhooks, cron_service, admin_http_rpc, diagnostics_otel, diagnostics_prom |
| **Migration / compatibility** | 2 | migrate_mark_xxxix, migrate_legacy_config |
| **Local-dev (scaffolded for testing)** | 2 | test_support, test_e2e_helpers |

## Manifest contract

Every extension **must** have a `jarvis.plugin.json` at its root. Minimal:

```json
{
  "id": "memory_wiki",
  "kind": "memory",
  "version": "0.1.0",
  "description": "Persistent wiki compiler and Obsidian-friendly knowledge vault."
}
```

Full schema validated by `tools/ci/check_manifests.py`. See
[`docs/development/plugin-manifest.md`](../docs/development/plugin-manifest.md) (Phase 1).

## Import rules (enforced by `tools/ci/check_imports.py`)

- ✅ `from jarvis_sdk import ...`
- ✅ `from . import sibling_module` (within same package)
- ❌ `from extensions.other_extension import ...` (cross-extension)
- ❌ `from packages.something import ...` (except `jarvis_sdk`)
- ❌ `import main`, `import ui`, `import or_client` (legacy modules being migrated)

## Phasing

| Phase | What fills in |
|---|---|
| 1 | First proof extension (memory_core) |
| 2 | (legacy `actions/` layer was fully removed) |
| 3 | (skills/ are separate, but extensions start to declare tool metadata) |
| 4 | memory_core, memory_lancedb, memory_wiki |
| 5 | First channel (telegram) |
| 6 | Providers ported as needed (OpenClaw has 80+; JARVIS focuses on memory + telegram first) |
| 7 | Media extensions (none yet — OpenClaw has image_generation-core, video_generation-core, etc.) |
| 9 | Remaining channels + providers |
| 10 | cron, webhooks, admin_http_rpc, diagnostics |
| 12 | test_support, test_e2e_helpers |
