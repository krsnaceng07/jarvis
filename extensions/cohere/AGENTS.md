# Cohere Provider Extension (JARVIS)

Minimum scaffold matching the OpenClaw `extensions/cohere/`
shape. The OpenClaw source is 11 files; this
Python port ships a focused subset.

## Parity status (vs `openclaw-main/extensions/cohere/`)

| OpenClaw | JARVIS | Notes |
|---|---|---|
| `index.ts` (entrypoint) | `__init__.py` + `plugin.py` | stub entry |
| `ProviderPlugin` descriptor | `CohereProvider` dataclass | shape equivalent |
| Streaming client | deferred | Phase 5.16 |
| Model catalog | `default_model` + `list_models()` stub | Phase 5.16 expands |
| Tool-use adapter | deferred | Phase 5.16 |
| Media understanding | deferred | Phase 5.16 |
| Embedding adapter | deferred | Phase 5.16 |

## Auth

API key: `COHERE_API_KEY` (read at provider init time).

## Base URL

`https://api.cohere.ai/compatibility/v1` (OpenAI-compatible).

The minimum-scaffold is loadable + discoverable; the full
streaming + tool-use surface lands in Phase 5.16.
