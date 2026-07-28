# Microsoft Foundry Provider Extension (JARVIS)

Minimum scaffold matching the OpenClaw `extensions/microsoft-foundry/`
shape. The OpenClaw source is 16 files; this
Python port ships a focused subset.

## Parity status (vs `openclaw-main/extensions/microsoft-foundry/`)

| OpenClaw | JARVIS | Notes |
|---|---|---|
| `index.ts` (entrypoint) | `__init__.py` + `plugin.py` | stub entry |
| `ProviderPlugin` descriptor | `MicrosoftFoundryProvider` dataclass | shape equivalent |
| Streaming client | deferred | Phase 5.16 |
| Model catalog | `default_model` + `list_models()` stub | Phase 5.16 |

## Auth

API key: `FOUNDRY_API_KEY` (read at provider init time).

## Base URL

`https://api.foundry.microsoft.com/v1` (OpenAI-compatible).

The minimum-scaffold is loadable + discoverable; the full
streaming + tool-use surface lands in Phase 5.16.
