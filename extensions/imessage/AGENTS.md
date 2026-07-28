# iMessage Channel Extension (JARVIS)

Minimum scaffold matching the OpenClaw `extensions/imessage/`
shape. The OpenClaw source is 19 files; this
Python port ships a focused subset.

## Parity status (vs `openclaw-main/extensions/imessage/`)

| OpenClaw | JARVIS | Notes |
|---|---|---|
| `index.ts` (entrypoint) | `__init__.py` + `plugin.py` | stub entry |
| `ChannelPlugin` descriptor | `iMessagePlugin` dataclass | shape equivalent |
| Send / listen | `send()` + `listen()` abstract stubs | Phase 5.16 |
| Media routing | deferred | Phase 5.16 |
| Doctor contract | `doctor.py` returns healthy stub | Phase 5.16 |
| Runtime singleton | `runtime.py` `set/get/reset` | shape equivalent |

## Auth

Env vars: `IMESSAGE_BRIDGE_URL, IMESSAGE_BRIDGE_TOKEN` (read at init time).

## Base URL

`http://localhost:1234`

The minimum-scaffold is loadable + discoverable; the full
send + listen + media surface lands in Phase 5.16.
