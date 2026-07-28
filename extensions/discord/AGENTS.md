# Discord Channel Extension (JARVIS)

Minimum scaffold matching the OpenClaw `extensions/discord/`
shape. The OpenClaw source is 631 files; this Python port
ships a focused subset:

- `openclaw.plugin.json` — manifest with `kind: channel` +
  `contracts.channel: true` + a config schema for
  `bot_token` + `application_id` + `polling_interval_sec`.
- `pyproject.toml` — `jarvis-discord` workspace member;
  depends on `httpx` (transport) + `jarvis-plugin-sdk`.
- `__init__.py` — public re-exports of the plugin
  descriptor + runtime + doctor contract.
- `plugin.py` — `DiscordPlugin(ChannelPlugin)` descriptor
  with id, name, kind, poll interval, on_message callback,
  start() no-op stub.
- `runtime.py` — `DiscordRuntime` long-poll loop + module
  singleton + `set_discord_runtime` / `get_discord_runtime`
  setters (matches the OpenClaw `runtime-setter-api.ts`
  shape).
- `doctor.py` — `discord_doctor_contract()` returns the
  channel wiring state (status, channel, runtimePresent,
  lastTick) for the host's doctor surface.

## Parity status (vs `openclaw-main/extensions/discord/`)

| OpenClaw | JARVIS | Notes |
|---|---|---|
| `index.ts` (entrypoint) | `__init__.py` + `plugin.py` | stub entry |
| `channel-plugin-api.ts` (Plugin descriptor) | `DiscordPlugin` dataclass | shape equivalent |
| `runtime-setter-api.ts` | `set_discord_runtime` / `get_discord_runtime` | shape equivalent |
| `doctor-contract-api.ts` | `discord_doctor_contract()` | shape equivalent |
| `account-inspect-api.ts` | deferred | Phase 5.16 |
| `activities-api.ts` | deferred | Phase 5.16 |
| `subagent-hooks-api.ts` | deferred | Phase 5.16 |
| `transcripts-source-api.ts` | deferred | Phase 5.16 |
| `directory-contract-api.ts` | deferred | Phase 5.16 |
| `secret-contract-api.ts` | deferred | Phase 5.16 |
| `security-audit-contract-api.ts` | deferred | Phase 5.16 |
| `session-binding-contract-api.ts` | deferred | Phase 5.16 |
| `session-key-api.ts` | deferred | Phase 5.16 |
| `setup-entry.ts` | deferred | Phase 5.16 |
| `setup-plugin-api.ts` | deferred | Phase 5.16 |
| `miniapp-api.ts` | deferred | Phase 5.16 |
| `update-offset-runtime-api.ts` | deferred | Phase 5.16 |
| `index.test.ts` (4 tests) | deferred (Phase 5.16) |  |

The minimum-scaffold is loadable + testable + wired into
the gateway poll loop; the full surface lands in
Phase 5.16 (the channel port).
