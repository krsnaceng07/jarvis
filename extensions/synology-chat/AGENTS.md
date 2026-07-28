# Synology Chat Channel Extension (JARVIS)

Minimum scaffold matching the OpenClaw `extensions/synology-chat/`
shape. The OpenClaw source is 38 files; this
Python port ships a focused subset.

## Parity status (vs `openclaw-main/extensions/synology-chat/`)

| OpenClaw | JARVIS | Notes |
|---|---|---|
| `index.ts` (entrypoint) | `__init__.py` + `plugin.py` | stub entry |
| `ChannelPlugin` descriptor | `SynologyChatPlugin` dataclass | shape equivalent |
| Send / listen | `send()` + `listen()` abstract stubs | Phase 5.16 |
| Doctor contract | `doctor.py` returns healthy stub | Phase 5.16 |
| Runtime singleton | `runtime.py` `set/get/reset` | shape equivalent |

## Auth

Env vars: `SYNOLOGY_CHAT_WEBHOOK_URL, SYNOLOGY_CHAT_TOKEN` (read at init time).

## Base URL

`https://your-nas:5001`

The minimum-scaffold is loadable + discoverable; the full
send + listen + media surface lands in Phase 5.16.
