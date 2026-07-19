# tool_reminder Plugin Guide

Read this before any change under `extensions/tool_reminder/`. These are intentional
maintainer decisions, not incidental implementation. Also read `extensions/AGENTS.md`
for the plugin boundary rules.

## Scope

- **Phase 1B:** Windows-only. Uses `schtasks` to schedule a one-shot task that runs
  a small `pythonw.exe` script (beep + toast + self-delete) at the requested time.
- **Phase 9 (target):** Cross-platform via the `cron` extension (Linux/macOS) plus
  `launchd` for macOS specifically. The Windows path stays as-is.

## Reliability Invariants

- **Past-time rejection.** If the requested `target_dt <= now`, return
  `Err("That time is already in the past.", code="TIME_IN_PAST")`. Never schedule
  in the past.
- **Format validation.** Date `YYYY-MM-DD`, time `HH:MM` (24h). Use
  `datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M")` and catch `ValueError`
  → return `Err("I couldn't understand that date or time format.", code="BAD_FORMAT")`.
- **No silent swallow.** Every `try/except` either returns an `Err` with a
  specific code, or `contextlib.suppress(Exception)` for cleanup paths only.
- **One-shot tasks only.** The task has `MultipleInstancesPolicy=IgnoreNew` and
  the script `os.remove(__file__)`s itself after running. We never accumulate
  orphan tasks.
- **`schtasks /Create /XML /F`.** Always `/F` (force overwrite) and `/XML` (not
  the legacy `/SC` form). Use UTF-16 encoding for the XML file.
- **Cleanup on failure.** If `schtasks` returns non-zero, delete the temp
  script. If writing the XML fails, delete both. Never leave temp files
  behind.
- **Self-deleting script.** The notification script must `os.remove(__file__)`
  after running. Wrap in `try/except` so a `PermissionError` doesn't crash it.

## Security Invariants

- **No shell injection.** The `message` is sanitized: strip all quotes, cap at
  200 chars. The XML is rendered with f-strings; never inject untrusted input
  into XML or shell commands without sanitization.
- **`schtasks` is called with `shell=True`.** The task name is derived from
  `target_dt` (no user input). The XML path and script path are derived from
  `temp_dir` + a deterministic task name. No command injection surface.
- **WakeToRun=true.** The task wakes the PC from sleep to fire the reminder.
  This is a power-consumption decision; document it in `jarvis extensions info`.

## Context And Authorization

- **Pairing is local-only.** Reminders are operator-local (they notify the
  Windows session, not a remote channel). No pairing/allowlist config required.
- **Time zone is the local clock.** `datetime.now()` returns the system local
  time. We do NOT store a timezone in the reminder; the user's PC clock is the
  source of truth. (Phase 9 will revisit when adding cron/launchd.)

## Review Standard

- Reminder behavior PRs need real Windows proof. Run `python -c "from
  extensions.tool_reminder import entry; print(entry.id, entry.kind)"` and
  manually schedule a reminder for 1 minute from now, then verify the
  task fires.
- Reliability PRs (time-parse, past-rejection, schtasks-failure handling)
  need unit tests with `datetime` and `subprocess` mocked.

## Dependencies

- `pycaw` and `pyaudio` are NOT used. This extension is Windows-only and uses
  `winsound` (stdlib) + `win10toast` (third-party) for the notification sound + toast.
- `pythonw.exe` is preferred over `python.exe` for the scheduled task to avoid
  flashing a console window.
