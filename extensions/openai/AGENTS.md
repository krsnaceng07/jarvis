# OpenAI Provider Extension (JARVIS)

Minimum scaffold matching the OpenClaw `extensions/openai/`
shape. The OpenClaw source is 85 files; this Python port
ships a focused subset.

## Parity status (vs `openclaw-main/extensions/openai/`)

| OpenClaw | JARVIS | Notes |
|---|---|---|
| `index.ts` (entrypoint) | `__init__.py` + `plugin.py` | stub entry |
| `ProviderPlugin` descriptor | `OpenAIProvider` dataclass | shape equivalent |
| Streaming client | deferred | Phase 5.16 |
| Tool-use adapter | deferred | Phase 5.16 |
| Multi-account surface | deferred | Phase 5.16 |
| Image input adapter | deferred | Phase 5.16 |
| Reasoning / o-series | deferred | Phase 5.16 |
| Audio + Realtime | deferred | Phase 5.16 |

The minimum-scaffold is loadable + discoverable; the full
streaming + tool-use surface lands in Phase 5.16.
