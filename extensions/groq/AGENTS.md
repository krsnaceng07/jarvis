# Groq Provider Extension (JARVIS)

Minimum scaffold matching the OpenClaw `extensions/groq/`
shape. The OpenClaw source is 9 files; this
Python port ships a focused subset.

## Parity status (vs `openclaw-main/extensions/groq/`)

| OpenClaw | JARVIS | Notes |
|---|---|---|
| `index.ts` (entrypoint) | `__init__.py` + `plugin.py` | stub entry |
| `ProviderPlugin` descriptor | `GroqProvider` dataclass | shape equivalent |
| Streaming client | deferred | Phase 5.16 |
| Model catalog | `default_model` + `list_models()` stub | Phase 5.16 expands |
| Tool-use adapter | deferred | Phase 5.16 |
| Media understanding | deferred | Phase 5.16 |
| Embedding adapter | deferred | Phase 5.16 |

## Auth

API key: `GROQ_API_KEY` (read at provider init time).

## Base URL

`https://api.groq.com/openai/v1` (OpenAI-compatible).

The minimum-scaffold is loadable + discoverable; the full
streaming + tool-use surface lands in Phase 5.16.
