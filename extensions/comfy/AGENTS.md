# ComfyUI Provider Extension (JARVIS)

Minimum scaffold matching the OpenClaw `extensions/comfy/`
shape. The OpenClaw source is 16 files; this
Python port ships a focused subset.

## Parity status (vs `openclaw-main/extensions/comfy/`)

| OpenClaw | JARVIS | Notes |
|---|---|---|
| `index.ts` (entrypoint) | `__init__.py` + `plugin.py` | stub entry |
| `ProviderPlugin` descriptor | `ComfyUIProvider` dataclass | shape equivalent |
| Streaming client | deferred | Phase 5.16 |
| Model catalog | `default_model` + `list_models()` stub | Phase 5.16 |

## Auth

API key: `COMFY_HOST` (read at provider init time).

## Base URL

`http://localhost:8188`

The minimum-scaffold is loadable + discoverable; the full
streaming + tool-use surface lands in Phase 5.16.
