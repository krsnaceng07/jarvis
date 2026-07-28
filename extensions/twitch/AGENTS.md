# Twitch Channel Extension (JARVIS)

Minimum scaffold matching the OpenClaw `extensions/twitch/`
shape. The OpenClaw source is 12 files; this
Python port ships a focused subset.

## Parity status (vs `openclaw-main/extensions/twitch/`)

| OpenClaw | JARVIS | Notes |
|---|---|---|
| `index.ts` (entrypoint) | `__init__.py` + `plugin.py` | stub entry |
| `ChannelPlugin` descriptor | `TwitchPlugin` dataclass | shape equivalent |
| Send / listen | `send()` + `listen()` abstract stubs | Phase 5.16 |
| Media routing | deferred | Phase 5.16 |
| Doctor contract | `doctor.py` returns healthy stub | Phase 5.16 |
| Runtime singleton | `runtime.py` `set/get/reset` | shape equivalent |

## Auth

Env vars: `OPENCLAW_TWITCH_ACCESS_TOKEN` (read at init time).

## Base URL

`wss://irc.chat.twitch.tv:443`

The minimum-scaffold is loadable + discoverable; the full
send + listen + media surface lands in Phase 5.16.
