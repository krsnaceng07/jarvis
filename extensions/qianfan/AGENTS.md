# Qianfan (Baidu) Provider Extension (JARVIS)

Minimum scaffold matching the OpenClaw `extensions/qianfan/`
shape. The OpenClaw source is 4 files; this
Python port ships a focused subset.

## Parity status (vs `openclaw-main/extensions/qianfan/`)

| OpenClaw | JARVIS | Notes |
|---|---|---|
| `index.ts` (entrypoint) | `__init__.py` + `plugin.py` | stub entry |
| `ProviderPlugin` descriptor | `Qianfan(Baidu)Provider` dataclass | shape equivalent |
| Streaming client | deferred | Phase 5.16 |
| Model catalog | `default_model` + `list_models()` stub | Phase 5.16 |

## Auth

API key: `QIANFAN_API_KEY` (read at provider init time).

## Base URL

`https://qianfan.baidubce.com/v2` (OpenAI-compatible).

The minimum-scaffold is loadable + discoverable; the full
streaming + tool-use surface lands in Phase 5.16.
