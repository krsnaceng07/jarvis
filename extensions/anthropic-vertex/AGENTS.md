# Anthropic Vertex Provider Extension (JARVIS)

Minimum scaffold matching the OpenClaw `extensions/anthropic-vertex/`
shape. The OpenClaw source is 20 files; this
Python port ships a focused subset.

## Parity status (vs `openclaw-main/extensions/anthropic-vertex/`)

| OpenClaw | JARVIS | Notes |
|---|---|---|
| `index.ts` (entrypoint) | `__init__.py` + `plugin.py` | stub entry |
| `ProviderPlugin` descriptor | `AnthropicVertexProvider` dataclass | shape equivalent |
| Streaming client | deferred | Phase 5.16 |
| Model catalog | `default_model` + `list_models()` stub | Phase 5.16 |

## Auth

API key: `VERTEX_ANTHROPIC_KEY` (read at provider init time).

## Base URL

`https://us-central1-aiplatform.googleapis.com/v1`

The minimum-scaffold is loadable + discoverable; the full
streaming + tool-use surface lands in Phase 5.16.
