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
| **Tools** (action modules) | 12 | tool_browser, tool_filesystem, tool_shell, tool_desktop, tool_youtube, tool_flight, tool_reminder, tool_weather, tool_screenshot, tool_clipboard, tool_calendar, tool_code |
| **Productivity** (personal integrations) | 7 | obsidian, notion, github, calendar, tasks, reminders_macos, notes_macos |
| **Voice / talk** | 3 | talk_voice, voice_wake, voice_call |
| **Infrastructure / ops** | 5 | webhooks, cron_service, admin_http_rpc, diagnostics_otel, diagnostics_prom |
| **Migration / compatibility** | 2 | migrate_mark_xxxix, migrate_legacy_config |
| **Local-dev (scaffolded for testing)** | 2 | test_support, test_e2e_helpers |

## Manifest contract

Every extension **must** have a `jarvis.plugin.json` at its root. Minimal:

```json
{
  "id": "tool_weather",
  "kind": "tool",
  "version": "0.1.0",
  "description": "Current weather and forecasts via web_fetch with curl fallback."
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
| 1 | First proof extension (e.g. `tool_weather`) |
| 2 | All 17 current actions → extensions |
| 3 | (skills/ are separate, but extensions start to declare tool metadata) |
| 4 | memory_core, memory_lancedb, memory_wiki |
| 5 | First 2 channels (telegram, discord) |
| 6 | First 5 providers (openai, anthropic, google, openrouter, ollama) |
| 7 | Media extensions |
| 9 | Remaining channels + providers |
| 10 | cron, webhooks, admin_http_rpc, diagnostics |
| 12 | test_support, test_e2e_helpers |
