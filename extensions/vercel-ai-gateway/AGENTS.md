# Vercel AI Gateway Provider Extension (JARVIS)

Minimum scaffold matching the OpenClaw `extensions/vercel-ai-gateway/`
shape. The OpenClaw source is 14 files; this
Python port ships a focused subset.

## Parity status (vs `openclaw-main/extensions/vercel-ai-gateway/`)

| OpenClaw | JARVIS | Notes |
|---|---|---|
| `index.ts` (entrypoint) | `__init__.py` + `plugin.py` | stub entry |
| `ProviderPlugin` descriptor | `VercelAIGatewayProvider` dataclass | shape equivalent |
| Streaming client | deferred | Phase 5.16 |
| Model catalog | `default_model` + `list_models()` stub | Phase 5.16 |

## Auth

API key: `VERCEL_AI_GATEWAY_KEY` (read at provider init time).

## Base URL

`https://ai-gateway.vercel.sh/v1`

The minimum-scaffold is loadable + discoverable; the full
streaming + tool-use surface lands in Phase 5.16.
