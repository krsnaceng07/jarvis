# MS Teams Provider Extension (JARVIS)

Minimum scaffold matching the OpenClaw `extensions/msteams/`
shape. The OpenClaw source is 200 files; this
Python port ships a focused subset.

## Parity status (vs `openclaw-main/extensions/msteams/`)

| OpenClaw | JARVIS | Notes |
|---|---|---|
| `index.ts` (entrypoint) | `__init__.py` + `plugin.py` | stub entry |
| `ProviderPlugin` descriptor | `MSTeamsProvider` dataclass | shape equivalent |
| Streaming client | deferred | Phase 5.16 |
| Model catalog | `default_model` + `list_models()` stub | Phase 5.16 |

## Auth

API key: `MSTEAMS_TENANT_ID` (read at provider init time).

## Base URL

`https://graph.microsoft.com/v1.0` (OpenAI-compatible).

The minimum-scaffold is loadable + discoverable; the full
streaming + tool-use surface lands in Phase 5.16.
