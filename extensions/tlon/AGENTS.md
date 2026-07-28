# Tlon Channel Extension (JARVIS)

Minimum scaffold matching the OpenClaw `extensions/tlon/`
shape. The OpenClaw source is 72 files; this
Python port ships a focused subset.

## Parity status (vs `openclaw-main/extensions/tlon/`)

| OpenClaw | JARVIS | Notes |
|---|---|---|
| `index.ts` (entrypoint) | `__init__.py` + `plugin.py` | stub entry |
| `ChannelPlugin` descriptor | `TlonPlugin` dataclass | shape equivalent |
| Send / listen | `send()` + `listen()` abstract stubs | Phase 5.16 |
| Doctor contract | `doctor.py` returns healthy stub | Phase 5.16 |
| Runtime singleton | `runtime.py` `set/get/reset` | shape equivalent |

## Auth

Env vars: `TLON_SHIP_NAME, TLON_CODE` (read at init time).

## Base URL

`https://tlon.io`

The minimum-scaffold is loadable + discoverable; the full
send + listen + media surface lands in Phase 5.16.
