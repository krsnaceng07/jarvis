# LINE Channel Extension (JARVIS)

Minimum scaffold matching the OpenClaw `extensions/line/`
shape. The OpenClaw source is 13 files; this
Python port ships a focused subset.

## Parity status (vs `openclaw-main/extensions/line/`)

| OpenClaw | JARVIS | Notes |
|---|---|---|
| `index.ts` (entrypoint) | `__init__.py` + `plugin.py` | stub entry |
| `ChannelPlugin` descriptor | `LINEPlugin` dataclass | shape equivalent |
| Send / listen | `send()` + `listen()` abstract stubs | Phase 5.16 |
| Media routing | deferred | Phase 5.16 |
| Doctor contract | `doctor.py` returns healthy stub | Phase 5.16 |
| Runtime singleton | `runtime.py` `set/get/reset` | shape equivalent |

## Auth

Env vars: `LINE_CHANNEL_ACCESS_TOKEN, LINE_CHANNEL_SECRET` (read at init time).

## Base URL

`https://api.line.me/v2/bot`

The minimum-scaffold is loadable + discoverable; the full
send + listen + media surface lands in Phase 5.16.
