# Application Adapter Architecture & Interface Contract

Each desktop application is governed by a dedicated adapter implementing `BaseDesktopApplicationAdapter`.

## 1. Interface Contract (`src/desktop_automation/applications/base.py`)
- `app_name`: Canonical identifier (e.g. `"whatsapp"`, `"vscode"`, `"word"`).
- `can_handle(window_title, process_name)`: Returns true if the window belongs to this application.
- `get_process_names()`: List of known executable names (e.g. `["WhatsApp.Root.exe", "WhatsApp.exe"]`).
- `ensure_running_and_focused()`: Reuses existing window if running; launches if necessary.
- `execute_action(action, params, context)`: Executes application-specific domain action.
- `verify_action(action, params, before_state, after_state)`: Inspects physical UI state to verify success.

## 2. Adapter Registry
Adapters are registered with `DesktopRuntime` and discovered dynamically based on foreground window or user intent.
