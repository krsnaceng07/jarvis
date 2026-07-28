# Feishu Channel Extension (JARVIS)

Minimum scaffold matching the OpenClaw `extensions/feishu/`
shape. The OpenClaw source is 263 files; this
Python port ships a focused subset.

## Parity status (vs `openclaw-main/extensions/feishu/`)

| OpenClaw | JARVIS | Notes |
|---|---|---|
| `index.ts` (entrypoint) | `__init__.py` + `plugin.py` | stub entry |
| `ChannelPlugin` descriptor | `FeishuPlugin` dataclass | shape equivalent |
| Send / listen | `send()` + `listen()` abstract stubs | Phase 5.16 |
| Doctor contract | `doctor.py` returns healthy stub | Phase 5.16 |
| Runtime singleton | `runtime.py` `set/get/reset` | shape equivalent |

## Auth

Env vars: `FEISHU_APP_ID, FEISHU_APP_SECRET` (read at init time).

## Base URL

`https://open.feishu.cn`

The minimum-scaffold is loadable + discoverable; the full
send + listen + media surface lands in Phase 5.16.
