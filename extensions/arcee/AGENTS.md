# Arcee Provider Extension (JARVIS)

Minimum scaffold matching the OpenClaw `extensions/arcee/`
shape. The OpenClaw source is 11 files; this
Python port ships a focused subset.

## Parity status (vs `openclaw-main/extensions/arcee/`)

| OpenClaw | JARVIS | Notes |
|---|---|---|
| `index.ts` (entrypoint) | `__init__.py` + `plugin.py` | stub entry |
| `ProviderPlugin` descriptor | `ArceeProvider` dataclass | shape equivalent |
| Streaming client | deferred | Phase 5.16 |
| Model catalog | `default_model` + `list_models()` stub | Phase 5.16 |

## Auth

API key: `ARCEE_API_KEY` (read at provider init time).

## Base URL

`https://api.arcee.ai/v1` (OpenAI-compatible).

The minimum-scaffold is loadable + discoverable; the full
streaming + tool-use surface lands in Phase 5.16.
