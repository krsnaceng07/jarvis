# Amazon Bedrock Provider Extension (JARVIS)

Minimum scaffold matching the OpenClaw `extensions/amazon-bedrock/`
shape. The OpenClaw source is 100 files; this
Python port ships a focused subset.

## Parity status (vs `openclaw-main/extensions/amazon-bedrock/`)

| OpenClaw | JARVIS | Notes |
|---|---|---|
| `index.ts` (entrypoint) | `__init__.py` + `plugin.py` | stub entry |
| `ProviderPlugin` descriptor | `AmazonBedrockProvider` dataclass | shape equivalent |
| Streaming client | deferred | Phase 5.16 |
| Model catalog | `default_model` + `list_models()` stub | Phase 5.16 |

## Auth

API key: `AWS_ACCESS_KEY_ID` (read at provider init time).

## Base URL

`https://bedrock-runtime.us-east-1.amazonaws.com` (OpenAI-compatible).

The minimum-scaffold is loadable + discoverable; the full
streaming + tool-use surface lands in Phase 5.16.
