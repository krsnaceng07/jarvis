# Nostr Channel Extension (JARVIS)

Minimum scaffold matching the OpenClaw `extensions/nostr/`
shape. The OpenClaw source is 63 files; this
Python port ships a focused subset.

## Parity status (vs `openclaw-main/extensions/nostr/`)

| OpenClaw | JARVIS | Notes |
|---|---|---|
| `index.ts` (entrypoint) | `__init__.py` + `plugin.py` | stub entry |
| `ChannelPlugin` descriptor | `NostrPlugin` dataclass | shape equivalent |
| Send / listen | `send()` + `listen()` abstract stubs | Phase 5.16 |
| Doctor contract | `doctor.py` returns healthy stub | Phase 5.16 |
| Runtime singleton | `runtime.py` `set/get/reset` | shape equivalent |

## Auth

Env vars: `NOSTR_RELAY_URL, NOSTR_PRIVATE_KEY` (read at init time).

## Base URL

`wss://relay.nostr.info`

The minimum-scaffold is loadable + discoverable; the full
send + listen + media surface lands in Phase 5.16.
