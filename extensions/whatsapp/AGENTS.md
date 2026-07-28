# WhatsApp Channel Extension (JARVIS)

Minimum scaffold matching the OpenClaw `extensions/whatsapp/`
shape. The OpenClaw source is 289 files; this
Python port ships a focused subset.

## Parity status (vs `openclaw-main/extensions/whatsapp/`)

| OpenClaw | JARVIS | Notes |
|---|---|---|
| `index.ts` (entrypoint) | `__init__.py` + `plugin.py` | stub entry |
| `ChannelPlugin` descriptor | `WhatsAppPlugin` dataclass | shape equivalent |
| Send / listen | `send()` + `listen()` abstract stubs | Phase 5.16 |
| Doctor contract | `doctor.py` returns healthy stub | Phase 5.16 |
| Runtime singleton | `runtime.py` `set/get/reset` | shape equivalent |

## Auth

Env vars: `WHATSAPP_BUSINESS_TOKEN, WHATSAPP_PHONE_ID` (read at init time).

## Base URL

`https://graph.facebook.com/v17.0`

The minimum-scaffold is loadable + discoverable; the full
send + listen + media surface lands in Phase 5.16.
