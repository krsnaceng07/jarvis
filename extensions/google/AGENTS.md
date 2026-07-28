# Google Gemini Provider Extension (JARVIS)

Minimum scaffold matching the OpenClaw `extensions/google/`
shape. The OpenClaw source is 89 files; this
Python port ships a focused subset.

## Parity status (vs `openclaw-main/extensions/google/`)

| OpenClaw | JARVIS | Notes |
|---|---|---|
| `index.ts` (entrypoint) | `__init__.py` + `plugin.py` | stub entry |
| `ProviderPlugin` descriptor | `GoogleGeminiProvider` dataclass | shape equivalent |
| Streaming client | deferred | Phase 5.16 |
| Model catalog | `default_model` + `list_models()` stub | Phase 5.16 |

## Auth

API key: `GOOGLE_API_KEY` (read at provider init time).

## Base URL

`https://generativelanguage.googleapis.com/v1`

The minimum-scaffold is loadable + discoverable; the full
streaming + tool-use surface lands in Phase 5.16.
