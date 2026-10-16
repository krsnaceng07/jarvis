# cron Plugin Guide

Read this before any change under `extensions/cron/`. Also read
`extensions/AGENTS.md` for the plugin boundary rules.

## Scope

- **Phase 2 (shipped).** Cross-platform scheduled jobs via
  `jarvis.cron.CronRunner`. Replaces the Windows-only `schtasks`
  path that used to live in the now-removed `tool_reminder`
  extension. Mirrors OpenClaw's `src/cron/`.
- **Phase 2.5 (target).** Real cron-expression parsing via
  `croniter` (currently a tiny in-process evaluator).
- **Phase 3+ (target).** `cron history` (audit log of past fires);
  retry with exponential backoff; pause/resume.

## Reliability Invariants

- **One job per id.** Adding the same id replaces the existing job
  (no duplicates). `remove(id)` is idempotent — second call
  returns `False`, not a crash.
- **Cron-table persistence.** Every add/remove writes through to the
  canonical shared SQLite state database so a host restart doesn't lose
  scheduled work. Explicit `.json` paths are read/write compatibility only.
- **Stub handler on reload.** When the table reloads from JSON, the
  handler is replaced with a no-op (we can't persist a function).
  The host must re-attach live handlers after reload.
- **Threading.** All access goes through `self._mu`. Reads and
  writes are atomic at the dict level.

## Security Invariants

- **No network.** Cron is local-only.
- **No `shell=True`.** Cron expressions are parsed in-process; job
  handlers are Python callables.
- **Operator-only slash command.** `expose_sender_is_owner=True` on
  the `/cron` command.

## Context And Authorization

- **No pairing/allowlist config.** The operator is the only user
  in Phase 2.
- **One table per workspace.** Default path is the canonical
  `$JARVIS_STATE_DIR/jarvis.sqlite` database. Never share a table across
  workspaces.

## Review Standard

- Schedule format changes (cron grammar, ISO parsing) need tests
  that exercise the boundary cases (DST, leap seconds, etc.).
- Persistence changes (schema bumps) need a migration path; never
  silently drop user data.

## Dependencies

- `json`, `threading`, `pathlib` (stdlib).
- No third-party packages. Phase 2.5 adds `croniter` for the
  parser and `pytz` for timezones.
