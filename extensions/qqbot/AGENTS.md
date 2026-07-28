# QQ Bot Channel Extension (JARVIS)

Minimum scaffold matching the OpenClaw `extensions/qqbot/`
shape. The OpenClaw source is 15 files; this
Python port ships a focused subset.

## Parity status (vs `openclaw-main/extensions/qqbot/`)

| OpenClaw | JARVIS | Notes |
|---|---|---|
| `index.ts` (entrypoint) | `__init__.py` + `plugin.py` | stub entry |
| `ChannelPlugin` descriptor | `QQBotPlugin` dataclass | shape equivalent |
| Send / listen | `send()` + `listen()` abstract stubs | Phase 5.16 |
| Media routing | deferred | Phase 5.16 |
| Doctor contract | `doctor.py` returns healthy stub | Phase 5.16 |
| Runtime singleton | `runtime.py` `set/get/reset` | shape equivalent |

## Auth

Env vars: `QQBOT_APP_ID, QQBOT_APP_SECRET` (read at init time).

## Base URL

`https://api.sgroup.qq.com`

The minimum-scaffold is loadable + discoverable; the full
send + listen + media surface lands in Phase 5.16.
