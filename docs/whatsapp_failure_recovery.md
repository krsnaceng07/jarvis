# WhatsApp Failure Modes & Self-Healing Recovery Matrix

**Architecture:** Self-Healing & Truthfulness Engine  
**OpenClaw Parity:** State-aware recovery preventing blind loops and false claims.  

---

## 1. Failure Modes & Self-Healing Protocols

| Failure Code | Observed Symptom | Root Cause | Self-Healing Recovery Protocol |
|:---|:---|:---|:---|
| `APPLICATION_NOT_RUNNING` | Process not in task list. | Application was closed. | Execute URI protocol `start whatsapp:`. Wait up to 5s for top-level window to materialize, then unminimize and focus. |
| `APPLICATION_MINIMIZED` | HWND at `(-32000, -32000)`, `IsIconic(hwnd) == True`. | WhatsApp minimized in Windows taskbar. | Call `ShowWindow(hwnd, SW_RESTORE)`. Wait 150ms. Bypasses Windows foreground lock via `AttachThreadInput` + Alt key event. |
| `FOREGROUND_LOCK_BLOCKED` | `SetForegroundWindow` returns 0 or taskbar icon flashes yellow without focusing. | Windows OS `SPI_SETFOREGROUNDLOCKTIMEOUT` foreground lock. | 1. Attach current thread input to foreground thread.<br>2. Simulate `keybd_event(0x12, 0, 0, 0)` (Alt down).<br>3. Call `BringWindowToTop` + `SetForegroundWindow`.<br>4. Release Alt and detach threads.<br>5. Verify `user32.GetForegroundWindow() == hwnd`. |
| `UTILITY_WINDOW_CONFUSION` | Window detector picks 1x1 dummy window (`GDI+ Window`). | GDI+ helper window returned first in Z-order. | Filter out windows matching `gdi+`, `default ime`, `msctfime ui`, or 1x1 dimensions. Prioritize windows matching title `"WhatsApp"`. |
| `CONTACT_NOT_FOUND` | Search results empty. | Typo in contact name or contact not saved. | **Do NOT guess or send to top random result.** Return `ok=False`, inform user that contact was not found. |
| `AMBIGUOUS_CONTACTS` | Multiple contacts match query. | Common first name (e.g. "Krishna"). | Stop execution. Present candidate names to user and request clarification. |
| `WRONG_CHAT_ACTIVE` | Active chat header does not match target. | Previous conversation was open. | Explicitly invoke `search_contact`, press Down, press Enter, and re-verify chat header matches recipient. |
| `FOCUS_LOST_MID_ACTION` | Foreground window changes between open and paste. | User clicked another window or popup appeared. | **STRICT SAFETY GATE**: Check `is_foreground()` immediately before paste and Enter. If lost, re-focus. If still lost, **ABORT** without typing. |
| `DUPLICATE_CALL_LOOP` | Model calls `whatsapp_send_message` multiple times in one turn. | Model hallucination or lack of turn fulfillment marker. | Idempotency filter detects identical `{recipient, message}` sent $< 5$s ago $\to$ returns `[SKIPPED: Duplicate call. Message already sent]` and directs model to speak to user. |

---

## 2. Truthful Reporting Invariant

JARVIS strictly reports one of:
- `COMPLETED_VERIFIED`: Foreground was acquired, text pasted, Enter pressed, and recipient header verified.
- `BLOCKED`: WhatsApp could not acquire foreground $\to$ keystrokes aborted to protect other open windows.
- `FAILED`: Parameter or application error.

**Under no condition does JARVIS report success when keystrokes were blocked or unverified.**
