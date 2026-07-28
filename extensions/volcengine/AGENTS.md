# Volcengine Provider Extension (JARVIS)

Minimum scaffold matching the OpenClaw `extensions/volcengine/`
shape. The OpenClaw source is 13 files; this
Python port ships a focused subset.

## Parity status (vs `openclaw-main/extensions/volcengine/`)

| OpenClaw | JARVIS | Notes |
|---|---|---|
| `index.ts` (entrypoint) | `__init__.py` + `plugin.py` | stub entry |
| `ProviderPlugin` descriptor | `VolcengineProvider` dataclass | shape equivalent |
| Streaming client | deferred | Phase 5.16 |
| Model catalog | `default_model` + `list_models()` stub | Phase 5.16 |

## Auth

API key: `VOLCENGINE_API_KEY` (read at provider init time).

## Base URL

`https://ark.cn-beijing.volces.com/api/v3` (OpenAI-compatible).

The minimum-scaffold is loadable + discoverable; the full
streaming + tool-use surface lands in Phase 5.16.
