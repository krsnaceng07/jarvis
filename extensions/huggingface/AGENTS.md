# Huggingface Provider Extension (JARVIS)

Minimum scaffold matching the OpenClaw `extensions/huggingface/`
shape. The OpenClaw source is 9 files; this
Python port ships a focused subset.

## Parity status (vs `openclaw-main/extensions/huggingface/`)

| OpenClaw | JARVIS | Notes |
|---|---|---|
| `index.ts` (entrypoint) | `__init__.py` + `plugin.py` | stub entry |
| `ProviderPlugin` descriptor | `HuggingfaceProvider` dataclass | shape equivalent |
| Streaming client | deferred | Phase 5.16 |
| Model catalog | `default_model` + `list_models()` stub | Phase 5.16 expands |
| Tool-use adapter | deferred | Phase 5.16 |
| Media understanding | deferred | Phase 5.16 |
| Embedding adapter | deferred | Phase 5.16 |

## Auth

API key: `HUGGINGFACE_HUB_TOKEN` (read at provider init time).

## Base URL

`https://api-inference.huggingface.co/models` (OpenAI-compatible).

The minimum-scaffold is loadable + discoverable; the full
streaming + tool-use surface lands in Phase 5.16.
