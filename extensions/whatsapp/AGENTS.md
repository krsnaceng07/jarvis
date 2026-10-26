# WhatsApp Channel Extension (JARVIS)

Bidirectional WhatsApp channel. Transport is a Baileys Web (WhatsApp multi-device)
session owned by a Node sidecar; Python never speaks the WhatsApp protocol.

## Layout

| Path | Responsibility |
|---|---|
| `plugin.py` | `WhatsAppPlugin`: send/ack, listen, login, logout, auth state |
| `bridge/bridge.js` | Node sidecar: `listen`, `login`, `logout` modes; JSON-lines protocol |
| `bridge/package.json`, `bridge/package-lock.json` | Pinned Baileys deps (`npm install` in this dir) |
| `doctor.py` | Link/credential diagnosis + repair contract |

## Protocol

- Bridge stdout is JSON-lines, one object per line. Events: `listener_ready`,
  `connected`, `message`, `send_result`, `listener_closed`, `qr`, `pairing_code`.
- Bridge stdin accepts JSON-lines commands: `{"action": "send", ...}` and
  `{"action": "stop"}`.
- `send()` must wait for a real `send_result` ack and never report success for a
  bare stdin write. `listen()` must fail loudly when readiness never arrives.

## Auth

QR-linked Baileys credentials under
`~/.jarvis/credentials/whatsapp/<accountId>/creds.json` (created by
`jarvis channels login whatsapp`). There is no Graph API bot token; never ask for
`WHATSAPP_BUSINESS_TOKEN` / `WHATSAPP_PHONE_ID`. Link state is detected from
`registered`, `linked`, or `me.id` in `creds.json`.

## Config

`~/.jarvis/config.json` → `channels.whatsapp`: `enabled`, `accountId`, `authDir`,
`linked`, `who`, `dmPolicy` (`allowlist`/`open`), `allowFrom`, `selfChatMode`.

## Rules

- One bridge listener per account per process; reuse the `ChannelManager` plugin
  instance instead of spawning a second Node sidecar.
- `selfChatMode` admits owner-sent-to-self messages (`fromMe: true`) as input and
  suppresses the listener that JARVIS just sent (60s echo window).
- Losing `creds.json` means re-linking; logout clears local credentials and says
  so honestly (the phone may still list the device until removed there).
