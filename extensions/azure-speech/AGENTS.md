# Azure Speech Provider Extension (JARVIS)

Minimum scaffold matching the OpenClaw `extensions/azure-speech/`
shape. The OpenClaw source is 30 files; this
Python port ships a focused subset.

## Parity status (vs `openclaw-main/extensions/azure-speech/`)

| OpenClaw | JARVIS | Notes |
|---|---|---|
| `index.ts` (entrypoint) | `__init__.py` + `plugin.py` | stub entry |
| `ProviderPlugin` descriptor | `AzureSpeechProvider` dataclass | shape equivalent |
| Streaming client | deferred | Phase 5.16 |
| Model catalog | `default_model` + `list_models()` stub | Phase 5.16 |

## Auth

API key: `AZURE_SPEECH_KEY` (read at provider init time).

## Base URL

`https://eastus.tts.speech.microsoft.com` (OpenAI-compatible).

The minimum-scaffold is loadable + discoverable; the full
streaming + tool-use surface lands in Phase 5.16.
