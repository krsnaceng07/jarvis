# JARVIS Known Limitations & Host Constraints

**Documentation Target:** System capabilities, platform limitations, and honest boundaries  
**OpenClaw Reference:** Operational safety limits and platform support documentation

---

## 1. Platform-Specific Boundaries

### 1.1 Windows Core Audio (`ctypes` COM Interface)
- **Support**: Native Windows 10 and 11.
- **Limitation**: Direct endpoint access via `CLSID_MMDeviceEnumerator` and `IAudioEndpointVolume` is Windows-only. On Linux or macOS, volume queries fall back to platform tools (ALSA/PulseAudio/macOS osascript) or report verified hardware status as unsupported.
- **Exclusive Mode**: If a third-party audio driver or ASIO application locks the audio endpoint in exclusive mode, master volume adjustments may return an endpoint error. In this situation, JARVIS truthfully reports: `"The current volume could not be verified."`

### 1.2 Elevated UAC & Administrative Boundaries
- If a target application (e.g. Task Manager, an elevated Command Prompt, or an installer) is running with Administrator privileges, standard Win32 `SetForegroundWindow` and `SendInput` calls from a non-elevated JARVIS process may be blocked by Windows User Interface Privilege Isolation (UIPI).
- **Behavior**: JARVIS detects when foregrounding fails and informs the user that administrative privilege is required.

### 1.3 WhatsApp Desktop UI Automation
- WhatsApp Desktop is a packaged Windows App (UWP / WinUI3). While keyboard shortcuts (`Ctrl + F`, typing, `Enter`) work reliably once the window is focused, direct click automation depends on the window being visible on an active virtual desktop (not minimized to system tray).
- **Behavior**: The `WhatsAppAdapter` automatically restores and focuses the window before typing.

---

## 2. Resource & Execution Timeouts

| Operation Family | Default Timeout | Hard Ceiling | Behavior on Timeout |
| :--- | :--- | :--- | :--- |
| Read-only tools (`ls`, `read`, `grep`, `system_info`) | 15s | 30s | Fails with explicit timeout message. |
| Coding tools (`write`, `edit`, `mkdir`, `remove_path`) | 30s | 60s | Fails and triggers self-healing path recovery. |
| Shell execution (`exec`) | 30s | 300s | Configurable via `timeout_ms`; aborts process if exceeded. |
| Audio & volume controls | 15s | 15s | Fails immediately if COM endpoint unresponsive. |
| Live web search (`web_search`) | 15s | 30s | Times out gracefully and returns query error. |

---

## 3. Truthfulness Guarantee

Whenever any hardware, network, or permission boundary is reached:
- **JARVIS NEVER invents volume percentages.**
- **JARVIS NEVER invents file contents or execution success.**
- **JARVIS reports the exact error and asks the user for assistance or retry.**
