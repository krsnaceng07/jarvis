# telegram Plugin Guide

Read this before any change under `extensions/telegram/`. Also read
`extensions/AGENTS.md` for the plugin boundary rules.

## Scope

- **Phase 3 (shipped).** Simplified Telegram channel: `send` +
  `listen` (long-polling) + operator pairing on first message +
  `/jarvis <text>` slash command routing. Mirrors OpenClaw's
  `extensions/telegram/` shape.
- **Phase 4+ (target).** Full OpenClaw parity: account snapshots,
  allow-list, inline buttons, threads, voice, multiple accounts.

## Reliability Invariants

- **Pairing is one-shot.** The first inbound message from any
  chat sets `paired_chat_id`. Subsequent messages from other
  chats are still delivered to the callback, but the operator can
  reset the pair via `jarvis telegram setup --reset`.
- **No exceptions leak.** `send()` returns `{"ok": false, "error": ...}`
  on any failure. `listen()` logs + retries on transient errors.
- **Polling backoff.** On `getUpdates` failure we sleep
  `interval * 5` seconds (5x the normal interval) before retrying.
  Prevents tight-loop hammering when Telegram is down.

## Security Invariants

- **Bot token is operator-secret.** Stored at
  `~/.jarvis/telegram.json` with mode 0600 on Unix (Windows
  inherits the user's ACL). Never logged.
- **All outbound calls are HTTPS.** Telegram Bot API is TLS-only;
  we never downgrade.
- **No shell injection.** `subprocess` is not used; all I/O is
  `httpx.get/post` with a dict body.

## Context And Authorization

- **Single active chat per workspace.** The paired chat_id is the
  "owner" — outbound `send` defaults to it. Other chats can
  receive messages but the slash router only responds to the
  paired chat (operator-only).
- **No pairing handshake.** Phase 3 uses the simplest possible
  pairing (first message wins). Phase 4 will add an explicit
  `/pair <code>` flow that mirrors OpenClaw's `PAIRING_APPROVED_MESSAGE`.

## Review Standard

- Adding new outbound API calls (e.g. `sendPhoto`, `editMessageText`):
  follow the existing `httpx.post` pattern + `data.get("ok")` check.
- Polling interval changes: keep the lower bound at 1 second
  (Telegram's rate limit on `getUpdates` is generous but no need
  to be wasteful).

## Dependencies

- `httpx` (required; only imported lazily so the plugin loads even
  if httpx is missing — `send`/`listen` return error in that case).
- No third-party packages beyond httpx.
