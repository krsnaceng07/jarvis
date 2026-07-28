# IRC Channel Extension (JARVIS)

Minimum scaffold matching the OpenClaw `extensions/irc/`
shape. The OpenClaw source is 16 files; this
Python port ships a focused subset.

## Parity status (vs `openclaw-main/extensions/irc/`)

| OpenClaw | JARVIS | Notes |
|---|---|---|
| `index.ts` (entrypoint) | `__init__.py` + `plugin.py` | stub entry |
| `ChannelPlugin` descriptor | `IRCPlugin` dataclass | shape equivalent |
| Send / listen | `send()` + `listen()` abstract stubs | Phase 5.16 |
| Media routing | deferred | Phase 5.16 |
| Doctor contract | `doctor.py` returns healthy stub | Phase 5.16 |
| Runtime singleton | `runtime.py` `set/get/reset` | shape equivalent |

## Auth

Env vars: `IRC_HOST, IRC_PORT, IRC_TLS, IRC_NICK, IRC_USERNAME, IRC_REALNAME, IRC_PASSWORD` (read at init time).

## Base URL

`irc://localhost:6667`

The minimum-scaffold is loadable + discoverable; the full
send + listen + media surface lands in Phase 5.16.
