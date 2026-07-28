# Slack Channel Extension (JARVIS)

Minimum scaffold matching the OpenClaw `extensions/slack/`
shape. The OpenClaw source is 331 files; this
Python port ships a focused subset.

## Parity status (vs `openclaw-main/extensions/slack/`)

| OpenClaw | JARVIS | Notes |
|---|---|---|
| `index.ts` (entrypoint) | `__init__.py` + `plugin.py` | stub entry |
| `ChannelPlugin` descriptor | `SlackPlugin` dataclass | shape equivalent |
| Send / listen | `send()` + `listen()` abstract stubs | Phase 5.16 |
| Doctor contract | `doctor.py` returns healthy stub | Phase 5.16 |
| Runtime singleton | `runtime.py` `set/get/reset` | shape equivalent |

## Auth

Env vars: `SLACK_BOT_TOKEN, SLACK_APP_TOKEN` (read at init time).

## Base URL

`https://slack.com/api`

The minimum-scaffold is loadable + discoverable; the full
send + listen + media surface lands in Phase 5.16.
