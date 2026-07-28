# Cloudflare AI Gateway Provider Extension (JARVIS)

Minimum scaffold matching the OpenClaw `extensions/cloudflare-ai-gateway/`
shape. The OpenClaw source is 12 files; this
Python port ships a focused subset.

## Parity status (vs `openclaw-main/extensions/cloudflare-ai-gateway/`)

| OpenClaw | JARVIS | Notes |
|---|---|---|
| `index.ts` (entrypoint) | `__init__.py` + `plugin.py` | stub entry |
| `ProviderPlugin` descriptor | `CloudflareAIGatewayProvider` dataclass | shape equivalent |
| Streaming client | deferred | Phase 5.16 |
| Model catalog | `default_model` + `list_models()` stub | Phase 5.16 |

## Auth

API key: `CLOUDFLARE_AI_GATEWAY_KEY` (read at provider init time).

## Base URL

`https://gateway.ai.cloudflare.com/v1` (OpenAI-compatible).

The minimum-scaffold is loadable + discoverable; the full
streaming + tool-use surface lands in Phase 5.16.
