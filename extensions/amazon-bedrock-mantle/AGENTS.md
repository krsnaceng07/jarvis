# Bedrock Mantle Provider Extension (JARVIS)

Minimum scaffold matching the OpenClaw `extensions/amazon-bedrock-mantle/`
shape. The OpenClaw source is 50 files; this
Python port ships a focused subset.

## Parity status (vs `openclaw-main/extensions/amazon-bedrock-mantle/`)

| OpenClaw | JARVIS | Notes |
|---|---|---|
| `index.ts` (entrypoint) | `__init__.py` + `plugin.py` | stub entry |
| `ProviderPlugin` descriptor | `BedrockMantleProvider` dataclass | shape equivalent |
| Streaming client | deferred | Phase 5.16 |
| Model catalog | `default_model` + `list_models()` stub | Phase 5.16 |

## Auth

API key: `MANTLE_API_KEY` (read at provider init time).

## Base URL

`https://bedrock.us-east-1.amazonaws.com` (OpenAI-compatible).

The minimum-scaffold is loadable + discoverable; the full
streaming + tool-use surface lands in Phase 5.16.
