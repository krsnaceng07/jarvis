# BytePlus Provider Extension (JARVIS)

Minimum scaffold matching the OpenClaw `extensions/byteplus/`
shape. The OpenClaw source is 12 files; this
Python port ships a focused subset.

## Parity status (vs `openclaw-main/extensions/byteplus/`)

| OpenClaw | JARVIS | Notes |
|---|---|---|
| `index.ts` (entrypoint) | `__init__.py` + `plugin.py` | stub entry |
| `ProviderPlugin` descriptor | `BytePlusProvider` dataclass | shape equivalent |
| Streaming client | deferred | Phase 5.16 |
| Model catalog | `default_model` + `list_models()` stub | Phase 5.16 |

## Auth

API key: `BYTEPLUS_API_KEY` (read at provider init time).

## Base URL

`https://ark.ap-southeast.bytepluses.com/api/v3`

The minimum-scaffold is loadable + discoverable; the full
streaming + tool-use surface lands in Phase 5.16.
