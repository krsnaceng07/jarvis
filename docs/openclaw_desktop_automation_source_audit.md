# OpenClaw Desktop Application Automation & Computer-Use Source Audit

**Repository:** `openclaw/openclaw` (commit `main`)
**Audit Target:** Computer-use subsystem, desktop control, UI tree, window management, accessibility, action verification, and recovery.

---

## 1. Computer-Use Architecture & Tool Contract

OpenClaw's computer-use architecture is built around three core pillars:

### A. The `computer` Agent Tool (`src/agents/tools/computer-tool.ts`, `computer-tool-schema.ts`)
- **Single Universal Entrypoint**: Models interact exclusively via the `computer` tool.
- **Sequential Execution Serialization (`serialize`)**: Desktop input and coordinate/frame state are queued strictly in model invocation order. This prevents race conditions where a click races a typing action or mouse button events interleave.
- **Post-Action Observation Loop (`AFTER_ACTION_SCREENSHOT_DELAY_MS`)**: Every action automatically captures a fresh screenshot and evaluates `refreshUnchangedFrame`. If pixels are identical to the previous frame, duplicate images are omitted and metadata is delivered (`"screen unchanged since previous frame (frameId ...)"`), preserving model context tokens.
- **Display Frame Binding (`displayFrameId`)**: Coordinate actions require an authoritative `frameId` from the most recent screenshot. Tokens from obsolete geometry or other displays fail closed.

### B. Action Families & Capabilities (`src/plugins/computer-use-contract.ts`)
- **Pointer/Mouse**: `left_click`, `right_click`, `middle_click`, `double_click`, `triple_click`, `mouse_move`, `left_click_drag`, `left_mouse_down`, `left_mouse_up`, `scroll`.
- **Keyboard**: `type` (exact unicode text), `key` (normalized key chords e.g. `ctrl+shift+p`), `hold_key` (held modifiers).
- **Window & Element (v2)**:
  - `list_apps`: Discovers running and installed applications with launch paths and PIDs.
  - `list_windows`: Enumerates desktop windows with bounds, titles, and PIDs.
  - `get_accessibility_tree`: Extracts UI accessibility hierarchy with element references (`elementRef`).
  - `get_window_state`: Retrieves deep window hierarchy with screenshots and controls.
  - `launch_app` / `kill_app`: Process lifecycle control.
  - `bring_to_front`: Window focus and restoration.
  - `set_value`: Background accessibility value injection.
  - `invoke_menu`: Path-based menu item invocation.
- **Browser Family**: `get_browser_state`, `browser_prepare`, `browser_navigate`, `browser_click`, `browser_type`, `browser_dialog`.
- **Recording & Trajectory**: `start_recording`, `stop_recording`, `replay_trajectory`.

### C. Fulfillers & Platform Implementations (`extensions/cua-computer/`)
- **macOS**: Embedded daemon in `OpenClaw.app` inheriting Accessibility & Screen Recording permissions.
- **Windows/Linux**: In-process CUA Driver SDK binding directly to the OS window manager and accessibility tree.
- **Mutation Verification**: Every action returns `effect`: `"confirmed"` | `"unverifiable"` | `"suspected_noop"`.
