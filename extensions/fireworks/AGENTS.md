# Fireworks AI Provider Extension (JARVIS)

Minimum scaffold matching the OpenClaw `extensions/fireworks/`
shape. The OpenClaw source is 14 files; this
Python port ships a focused subset.

## Parity status (vs `openclaw-main/extensions/fireworks/`)

| OpenClaw | JARVIS | Notes |
|---|---|---|
| `index.ts` (entrypoint) | `__init__.py` + `plugin.py` | stub entry |
| `ProviderPlugin` descriptor | `FireworksAIProvider` dataclass | shape equivalent |
| Streaming client | deferred | Phase 5.16 |
| Model catalog | `default_model` + `list_models()` stub | Phase 5.16 |

## Auth

API key: `FIREWORKS_API_KEY` (read at provider init time).

## Base URL

`https://api.fireworks.ai/inference/v1` (OpenAI-compatible).

The minimum-scaffold is loadable + discoverable; the full
streaming + tool-use surface lands in Phase 5.16.
