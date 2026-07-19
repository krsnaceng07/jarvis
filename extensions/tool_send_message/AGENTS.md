# tool_send_message Plugin Guide

Read this before any change under `extensions/tool_send_message/`. Also
read `extensions/AGENTS.md` for the plugin boundary rules.

## Scope

- **Phase 1C (shipped).** Universal messenger via pyautogui. WhatsApp,
  Instagram, Telegram, and a generic fallback for any Ctrl+F-searchable
  app (Messenger, Discord, Signal, etc.).
- **Phase 3+ (target).** Native platform APIs (e.g. `telegram-bot-api`,
  `whatsapp-business-api`) for non-visual sending. The pyautogui path
  stays for users who refuse to wire up API keys.

## Reliability Invariants

- **Dispatch on platform string, not exact name.** `whatsapp`, `wp`,
  `wapp` all map to WhatsApp; `instagram`, `ig`, `insta` to Instagram;
  `telegram`, `tg` to Telegram. Anything else falls through to the
  generic sender.
- **Never raise.** Every `try/except` returns a human-readable error
  string (not a crash) so the LLM can react.
- **Pyautogui FAILSAFE is ON.** Moving the mouse to a screen corner
  aborts the automation — this is the safety net for runaway typing.
- **Generic sender waits 2s after app-open.** Apps that load slowly
  (Discord, Signal) need time to render the contact search box.

## Security Invariants

- **No `shell=True`.** All `subprocess.run` calls (none today) would
  be list-form. `pyautogui` does not spawn shells.
- **Visual automation is operator-only.** A paired remote user must
  not be able to drive the operator's UI without explicit consent.
  This is enforced at the host level (single-live-session) in 1C;
  Phase 2 adds a per-session UI-automation allowlist.
- **Receiver + message_text both required.** We don't allow
  blank-receiver sends; typos would go to a wrong contact.

## Context And Authorization

- **No pairing/allowlist config.** Sends go to whatever the operator
  types; we do not enforce a contact allowlist in 1C.
- **Pyautogui is Windows-tested.** The Instagram path uses
  `webbrowser.open(...)` which is cross-platform but not visually
  verified on macOS or Linux.

## Review Standard

- New platform senders (e.g. Signal, Messenger) need a test that
  asserts the dispatch table routes the platform name correctly.
- Pyautogui sequence changes (wait times, key combos) need a manual
  test on Windows before merging.

## Dependencies

- `pyautogui` (required). Pins the FAILSAFE and PAUSE globals at
  import time.
- `webbrowser` (stdlib).
- `time` (stdlib).
