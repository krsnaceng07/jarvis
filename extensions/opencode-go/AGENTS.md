# OpenCode Go Provider Extension (JARVIS)

Minimum scaffold matching the OpenClaw `extensions/opencode-go/`
shape. The OpenClaw source is 17 files; this
Python port ships a focused subset.

## Parity status (vs `openclaw-main/extensions/opencode-go/`)

| OpenClaw | JARVIS | Notes |
|---|---|---|
| `index.ts` (entrypoint) | `__init__.py` + `plugin.py` | stub entry |
| `ProviderPlugin` descriptor | `OpenCodeGoProvider` dataclass | shape equivalent |
| Streaming client | deferred | Phase 5.16 |
| Model catalog | `default_model` + `list_models()` stub | Phase 5.16 |

## Auth

API key: `OPENCODE_GO_API_KEY` (read at provider init time).

## Base URL

`https://api.opencode.go/v1` (OpenAI-compatible).

The minimum-scaffold is loadable + discoverable; the full
streaming + tool-use surface lands in Phase 5.16.
