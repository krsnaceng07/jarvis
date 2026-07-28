# NVIDIA NIM Provider Extension (JARVIS)

Minimum scaffold matching the OpenClaw `extensions/nvidia/`
shape. The OpenClaw source is 10 files; this
Python port ships a focused subset.

## Parity status (vs `openclaw-main/extensions/nvidia/`)

| OpenClaw | JARVIS | Notes |
|---|---|---|
| `index.ts` (entrypoint) | `__init__.py` + `plugin.py` | stub entry |
| `ProviderPlugin` descriptor | `NVIDIANIMProvider` dataclass | shape equivalent |
| Streaming client | deferred | Phase 5.16 |
| Model catalog | `default_model` + `list_models()` stub | Phase 5.16 |

## Auth

API key: `NVIDIA_API_KEY` (read at provider init time).

## Base URL

`https://integrate.api.nvidia.com/v1` (OpenAI-compatible).

The minimum-scaffold is loadable + discoverable; the full
streaming + tool-use surface lands in Phase 5.16.
