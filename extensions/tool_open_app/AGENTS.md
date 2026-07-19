# tool_open_app Plugin Guide

Read this before any change under `extensions/tool_open_app/`. These are
intentional maintainer decisions, not incidental implementation. Also
read `extensions/AGENTS.md` for the plugin boundary rules.

## Scope

- **Phase 1C (shipped).** Cross-platform app launcher via the alias
  table + per-OS launcher. Mirrors the legacy `actions/open_app.py`
  behavior exactly.
- **Phase 3+ (target).** Add per-app arguments (e.g. `--new-window`)
  via a new `ToolParam` + a separate "deep-link" path.

## Reliability Invariants

- **No silent swallow with crash.** Every `try/except` either returns
  `False` (launcher failed) or `contextlib.suppress` for cleanup paths.
  We never let a `subprocess.CalledProcessError` or `pyautogui.FailSafeException`
  propagate to the LLM.
- **Alias table is case-insensitive.** The host may say "Chrome",
  "chrome", or "Google Chrome"; the table handles all three.
- **Two-pass launch.** If the alias-resolved binary fails, we retry
  with the raw `app_name` (some apps have no alias). Only return
  `LAUNCH_UNCONFIRMED` after both attempts.
- **Unsupported OS is a hard `Err`.** The plugin only knows Windows,
  macOS, Linux. Anything else returns `UNSUPPORTED_OS` — we don't
  guess or fall through to a generic shell-out.

## Security Invariants

- **`os.startfile` (Windows) is the first choice.** It uses the shell's
  registered handler with no user-input injection. The fallback to
  `pyautogui.press("win")` is for apps the shell doesn't know about.
- **`xdg-open`/`gtk-launch` (Linux) take untrusted input.** The
  `app_name` is passed positionally; we do NOT shell-construct the
  command. We use `subprocess.run([...])` with a list (no `shell=True`).
- **`pyautogui` is best-effort.** A `FailSafeException` (mouse in a
  corner) returns `False`, not a crash.

## Context And Authorization

- **No pairing/allowlist config.** App launching is operator-local; any
  paired remote user inherits the operator's launch surface.
- **No network calls.** The launcher never reaches the network; if
  the user asks for a web app, route to `tool_web_search` (browser
  open) instead.

## Review Standard

- Per-OS launcher PRs need a real OS test. Stubbed tests only cover
  the alias resolution + dispatch; the actual `subprocess.run` and
  `pyautogui` paths are integration-tested in Phase 4+ when we get a
  CI matrix.
- The `_APP_ALIASES` table is the source of truth for friendly names.
  Add a row, not a new conditional.

## Dependencies

- `subprocess`, `shutil`, `platform`, `time` (all stdlib).
- `pyautogui` is **optional** — only required for the Spotlight / Start
  menu fallback. The plugin works without it; only the fallback path
  degrades.
- No third-party packages.
