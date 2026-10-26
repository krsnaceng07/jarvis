
# JARVIS Desktop UI — Full Functional PRD
**Version:** 1.0  
**Date:** 24 October 2026  
**Purpose:** Rebuild the supplied Jarvis/Stonic-style desktop UI as a functional, maintainable desktop application, using the reference screenshot as the visual source of truth.

## 1. Executive Summary

Build a desktop-first Jarvis interface that closely reproduces the supplied reference screenshot while connecting to a real Python-based Jarvis/OpenClaw agent runtime. The result must not be a static mockup: visible controls must work, panels must reflect real state, asynchronous activity must be represented honestly, and unavailable backend capabilities must be clearly marked as unavailable rather than simulated.

**Primary visual target:** dark, near-black/navy desktop workspace; thin cyan outlines; subtle grid texture; cyan/blue holographic visualization; green, red, and cool-white signal paths; dense left-side satellite feed and headlines; central connected module stack and animated holographic assistant; lower central Visual Hub; tall right-side Voice/Agent/Notes panel.

**Important implementation rule:** the screenshot is authoritative for visible layout and styling. It is not evidence that any pictured integration already exists. For screen sharing, camera, voice, memory, agent orchestration, file access, or system controls, implement only real capabilities exposed by the backend. If an integration is missing, show a truthful disconnected/unavailable state and a clear setup action.

## 2. Product Goals

1. Reproduce the screenshot’s layout, hierarchy, colors, spacing, typography, panel proportions, and interaction affordances as closely as practical.
2. Keep the existing Python Jarvis/OpenClaw engine; do not rewrite the agent runtime merely to implement the UI.
3. Make every displayed interactive control have a defined behavior, loading state, success state, error state, and accessibility label.
4. Provide real-time updates from Python to the UI using WebSockets, with reconnect and stale-state handling.
5. Support voice interaction, agent status, memory/skills/character/settings navigation, visual hub, screen/camera observation where available, and chat/notes.
6. Make the implementation modular, testable, secure, and extendable without turning the UI into a monolithic component.
7. Prevent misleading UI: no fake live telemetry, fabricated headlines, pretend camera feed, or hard-coded “agent completed” status in production mode.

## 3. Non-Goals

- Rebuilding or replacing the existing Jarvis/OpenClaw backend.
- Claiming to reproduce proprietary internals from a screenshot.
- Implementing an actual satellite network or threat-intelligence service unless an approved data source is connected.
- Automatically controlling the user's computer without explicit permissions and visible status.
- Treating the generated/reference image as production-ready source code.
- Making a web-only site and calling it a native desktop application without a documented desktop shell.

## 4. User, Environment, and Platform

### Primary user
A desktop user who interacts with a personal AI assistant using voice and text, monitors its state, and invokes visual/screen/camera and agent tools.

### Initial target
- Desktop-first; Windows and Linux are primary targets unless the existing project specifies otherwise.
- Existing Jarvis engine is Python-based and currently follows or integrates with an OpenClaw-style architecture.
- UI runs locally and communicates with a local backend by default.
- Must support a development mode and a production mode.

### Desktop shell decision
Preferred integration, subject to a small architecture spike:
- React + TypeScript UI rendered in Qt WebEngine.
- PySide6 hosts the desktop window and provides controlled native integration.
- FastAPI runs as a local service or embedded process and exposes typed HTTP/WebSocket contracts.

**Architecture gate:** first inspect the current project for an existing Electron, Tauri, Qt, browser, or OpenClaw UI shell. Reuse the existing shell if it is stable and compatible. Do not add PySide6/Qt WebEngine as a second competing shell without a documented reason. The React UI technology remains the same regardless of shell.

## 5. Reference Screenshot — Visual Inventory

The reference is a 16:9-ish desktop screenshot with a black/navy background, thin luminous cyan borders, restrained glow, small uppercase labels, and a three-zone composition.

### 5.1 Global top bar
- Full-width horizontal header at the top.
- Left: small AI/logo mark and product name “Stonic AI” in the supplied reference.
- Nearby actions: Feedback, Manage Billing, Support.
- Center/right metadata: version string, Awareness toggle, Theme menu, Profile menu.
- Far right: native-window controls may appear depending on desktop shell.
- Keep the product name configurable; if this build is named Jarvis, use “JARVIS” consistently unless the owner explicitly wants “Stonic AI”.
- Header controls must be functional or omitted; do not render dead buttons.

### 5.2 Left column — SAT-LINK FEED
- Narrow, full-height column with cyan outline and subtle grid.
- Header: “SAT-LINK FEED”.
- Subheader row: “SATELLITE STREAM”, refresh icon, “EXPAND” control.
- Map mode controls: 2D, 3D, and map/expand affordance.
- Main visual: dark Earth/satellite-style map with glowing location markers and event indicators.
- Bottom map navigation: Today, Map, Search, Alerts, More.
- Below the map: “TODAY HEADLINES” section with refresh/filter-style icons and numbered headlines.
- The reference’s map and headlines may be sample visual modules. In production, display real connected data with source attribution, timestamps, loading/error/empty states. If no data provider is connected, label the map “Demo/Preview” or show an honest unavailable state.

### 5.3 Middle-left module connectors
Four compact rectangular modules placed vertically, connected to the central hologram by thin routed lines:
1. MEMORY — cyan/blue.
2. SKILLS — green.
3. CHARACTER — red.
4. SETTINGS — cool white/blue.

Each module includes an icon, uppercase label, color-coded outline/fill, and status dot/connector. The connectors should be decorative representations of actual module health only if status is real. Module cards must open their corresponding views or panels when clicked.

### 5.4 Central assistant / hologram panel
- Large outlined panel with clipped/chamfered corners and a faint grid.
- Centered particle-based holographic head/upper-body visual in blue/cyan.
- Status text near bottom, e.g. “Jarvis is listening”.
- Primary red “TERMINATE” button.
- Separate circular microphone control.
- Top of panel has a mode selector with “new”, “classic”, and a settings icon in the reference.
- State-dependent rendering is mandatory: idle, listening, processing/thinking, speaking, tool-running, interrupted, disconnected, error.
- “TERMINATE” must stop/cancel the current cancellable action or voice session after confirmation where appropriate; it must not silently kill the whole application.

### 5.5 Lower center — VISUAL HUB
- Wide panel below the assistant, aligned to the center workspace.
- Header contains “VISUAL HUB”, a readiness/status label, tabs such as “visual hub” and “gesture”, plus expand control.
- Main content is split: left side has a layered 3D schematic/diagram illustration; right side has “What do you want to see?”, a short instruction, and four suggested prompts:
  1. Draw a SpaceX Starship blueprint.
  2. Show how a black hole bends light.
  3. Look inside a fusion reactor.
  4. Plan a crewed mission to Mars.
- The examples are prompts, not claims that the feature is implemented. Clicking one must populate/submit the prompt according to the interaction contract.
- Bottom strip shows a horizontal library/history ticker with compact items and dates. Real items must come from actual saved history; otherwise show an empty state.

### 5.6 Right column — VOICE / AGENT / NOTES
- Tall, full-height panel with cyan border and dark grid background.
- Tab row: VOICE, AGENT, NOTES.
- Utility icons: add/new, history, terminal/command, expand/fullscreen, panel toggle (only include icons with defined behavior).
- Empty/ready state centered in the panel with robot icon, “SYSTEM READY”, and a short assistant greeting. Reference greeting is Hindi; product language should be configurable.
- Bottom composer: “Type to Stonic Voice...” placeholder in reference, attachment icon, send/up-arrow control.
- The panel must support scrollable conversation, streaming responses, message timestamps, user/assistant distinction, cancellation, errors, and retry.
- Voice, Agent, and Notes are distinct views backed by separate state/data models; switching tabs must not erase ongoing work.

### 5.7 Background and system styling
- Near-black/navy canvas; restrained cyan/teal glow.
- Fine grid texture, thin borders, clipped/chamfered corners on hero panels.
- Color roles: cyan for primary actions/active selection, green for healthy/connected, red for destructive/critical, blue for secondary system information, gray/white for neutral text.
- Keep glows subtle enough that text remains readable.
- No external watermark, screenshot border, camera/photo artifacts, or unrelated desktop content inside the application UI.
- The screenshot is a visual reference, not a requirement to use the exact “Stonic AI” branding if the app is Jarvis.

## 6. Layout and Responsive Behavior

### Desktop target
- Target canvas: 1536 × 864 reference-like desktop, plus validation at 1920 × 1080 and 1366 × 768.
- Layout should fill the application content area without accidental browser scrollbars.
- Use CSS Grid for the main composition; avoid absolute positioning for all major panels.
- Suggested logical grid: left rail about 18–21%, center workspace about 49–53%, right panel about 28–31%, adjusted by minimum widths and available viewport.
- The center workspace uses two rows: upper assistant/connectors region and lower Visual Hub.
- The right panel spans the full content height.
- Left column stacks satellite feed/map and headlines.
- Minimum supported content width must be explicitly tested. At smaller widths, collapse the left column into a drawer and keep the assistant/chat usable rather than allowing panels to overlap.
- Respect OS title bar/window controls and safe margins supplied by the desktop shell.
- All panels must support independent internal scrolling where needed; avoid page-level scroll where the reference shows a fixed dashboard.

### Scaling
- Use CSS `minmax()`, `clamp()`, grid/flex constraints, and design tokens.
- Avoid hard-coded pixel sizes for every element.
- The hologram canvas must resize with its container and preserve aspect ratio.
- Ensure text does not clip at Windows display scaling settings such as 100%, 125%, and 150%.

## 7. Design System

### 7.1 Design tokens
Create centralized CSS variables or Tailwind theme tokens for:
- Background: app, panel, elevated panel, input.
- Border: subtle, standard, active, critical.
- Text: primary, secondary, muted, disabled.
- Accent: cyan, teal, green, blue, red, amber.
- Radius: small cards, standard panels, hero/chamfer panels.
- Spacing scale: 4, 8, 12, 16, 20, 24, 32 px equivalents.
- Typography: UI sans-serif; optional monospace for telemetry and technical labels.
- Shadow/glow: subtle, active, critical.
- Motion duration/easing and reduced-motion fallback.

### 7.2 Typography
- Main labels are compact uppercase with modest letter spacing.
- Body text must remain readable at normal desktop distance; do not copy blurry/small text artifacts from the screenshot.
- Use a reliable bundled or system sans-serif font; monospace only for timestamps, telemetry, IDs, and technical status.
- Define type sizes for header, panel title, body, metadata, and micro-labels.
- Avoid relying on rasterized text or image text for any UI label.

### 7.3 Icons
- Use a consistent icon library (e.g. Lucide) or custom SVG set.
- Icons must be vector, aligned, have tooltips/accessible labels, and use consistent stroke widths.
- Do not use emoji as production icons.
- Every icon-only button needs a tooltip and accessible name.

### 7.4 Motion
- Hologram particles, connector pulses, map markers, and active tabs may animate.
- Animation must be performance-aware and respect `prefers-reduced-motion`.
- Pause nonessential animation when the window is hidden or the relevant panel is offscreen.
- No animation may block clicks, keyboard input, or screen-reader access.

## 8. Functional Requirements

### FR-001 — Application shell
- Launch into a stable desktop window with the dashboard.
- Show app/version and connection state.
- Handle minimize, maximize, close according to shell conventions.
- Closing behavior must be predictable; if a task or voice session is active, prompt only when data loss or an actual interruption is likely.
- Store UI preferences locally: theme, last selected tab, panel layout, and window size, subject to privacy policy.

### FR-002 — Header controls
- Feedback opens a feedback form or configured feedback destination.
- Manage Billing appears only if billing is relevant and configured; otherwise omit it or provide a disabled state with explanation.
- Support opens local help/docs or configured support.
- Awareness toggle changes an explicitly defined awareness/monitoring setting; show what it enables and when it is active.
- Theme menu supports available themes, at minimum the reference dark theme.
- Profile menu shows local user/profile state and relevant actions.
- Version is supplied by app metadata, not hard-coded in the component.

### FR-003 — Satellite/map feed
- Map supports 2D/3D switching only if both are implemented.
- Expand opens a larger map view.
- Refresh requests new data and indicates loading/success/failure.
- Map controls include keyboard-accessible equivalents.
- Search filters available map events; Alerts filters critical/alert events; Today filters the current-day feed; More opens remaining options.
- If no actual geospatial feed exists, use a clearly labelled preview mode and never imply that fabricated points are live satellite intelligence.

### FR-004 — Headlines
- Render title, number, source, timestamp, and optional summary.
- Refresh reloads configured source.
- Filters operate on real headline metadata.
- Headline clicks open a detail view or the configured source URL after safe URL validation.
- Loading, empty, stale, and error states are required.
- Do not invent real news. Demo content must be marked as demo.

### FR-005 — Module cards: Memory, Skills, Character, Settings
- Each card opens its dedicated view or route.
- Status indicator reflects real backend state: connected, degraded, unavailable, or loading.
- Connector lines visually link module cards to the assistant; animate only when the corresponding connection/event is active.
- Memory: show available memory search/management actions and provenance where supported; protect sensitive information and provide delete/export controls only when supported by backend policy.
- Skills: list installed skills, status, permissions, run capability, and errors. Skill execution requires confirmation for high-impact actions.
- Character: manage supported persona/voice/visual preferences without claiming it changes the underlying model beyond configured capabilities.
- Settings: expose theme, voice, permissions, backend connection, privacy, startup behavior, diagnostics, and other settings actually supported.
- If a view is not implemented, show “Not configured” with a setup path rather than an empty clickable shell.

### FR-006 — Assistant hologram and state machine
Implement a single explicit state machine:
- `idle`
- `listening`
- `transcribing`
- `thinking`
- `speaking`
- `tool_running`
- `waiting_for_permission`
- `cancelling`
- `cancelled`
- `disconnected`
- `error`

Transitions must be driven by backend events and user actions, not by arbitrary timers. Provide a fallback timeout for stale sessions and reconcile with backend state on reconnect. UI status text and animation must match state. “Jarvis is listening” must only appear while a real microphone capture session is active.

### FR-007 — Voice controls
- Microphone button requests permission when required and shows the permission outcome.
- Starting/stopping capture must connect to the actual voice service.
- Display listening/transcribing/thinking/speaking states.
- Support interruption/barge-in if the voice engine supports it.
- Show microphone disabled, busy, denied, unavailable, and device error states.
- Provide a visible mute/stop path.
- Never capture audio silently or imply that the microphone is active when it is not.

### FR-008 — Terminate/cancel
- Cancel the current request/session using a backend cancellation endpoint/event.
- If several tasks exist, identify which task will be cancelled.
- Destructive whole-agent shutdown must be a separate explicit action with confirmation.
- Update UI only after the backend acknowledges cancellation; show pending/error if not acknowledged.
- Preserve completed chat history and partial output according to backend behavior.

### FR-009 — Visual Hub
- Visual Hub and Gesture tabs are real tabs with independent state.
- Prompt suggestions are selectable; selection can populate the composer or submit after an explicit user action.
- Prompt execution shows queued/running/streaming/completed/failed/cancelled state.
- Support output types actually provided by backend: text, image, diagram, or structured visual.
- Expand opens a larger workspace; close returns to the dashboard without losing active task state.
- 3D layered diagram is either a real interactive Three.js scene or an honest illustration; do not make a static illustration appear to be a live model.
- Gesture mode must be hidden/disabled unless a gesture/camera pipeline is configured and permission is granted.
- History/library strip loads saved records and handles empty/loading/error states.

### FR-010 — Voice / Agent / Notes panel
**Voice**
- Conversation history, message composer, streaming response, stop generation, retry, copy, timestamps, and error state.
- Enter sends; Shift+Enter inserts a newline (unless configured otherwise).
- Composer supports attachment only for approved file types and size limits.
- Keep focus in composer after sending unless user action changes focus.

**Agent**
- Display active task, current step, tool activity, start time, progress only when meaningful progress is supplied, and final outcome.
- Show waiting-for-approval and blocked states.
- Do not manufacture percentages when backend cannot report progress.
- Allow opening task detail, cancelling cancellable tasks, and inspecting safe summaries of tool output.

**Notes**
- Create, edit, search, and delete notes if persistence exists.
- Auto-save must show saving/saved/error state.
- If notes are not backed by persistence, label them session-only.
- Switching tabs must preserve each tab's state.

### FR-011 — Chat composer
- Placeholder reflects selected mode.
- Send button disabled when empty or while action is disallowed.
- Enter/Shift+Enter behavior is consistent and configurable.
- Support keyboard navigation, clipboard paste, and attachment validation.
- Show streaming response without layout jumps.
- Prevent duplicate submissions on rapid click/Enter.

### FR-012 — Library/history ticker
- Shows recent saved visual tasks, sessions, or files with title and date.
- Items open their actual saved record.
- Horizontal scrolling supports mouse, touchpad, and keyboard.
- Truncate long titles with tooltip and accessible full text.
- Show loading/empty/error states; do not hard-code fake history in production.

### FR-013 — Notifications and errors
- Nonblocking toast for transient success/failure.
- Persistent status for backend disconnected, permissions missing, or task awaiting approval.
- Errors must be actionable and nontechnical where possible, with a technical detail expander for diagnostics.
- Avoid repeated toast storms; deduplicate repeated WebSocket errors.

### FR-014 — Permissions and privacy
- Request microphone, camera, screen-capture, filesystem, and automation permissions only when needed.
- Display capture indicators whenever microphone/camera/screen capture is active.
- Offer stop/pause controls.
- Do not store raw media or screenshots unless a defined feature requires it and policy permits it.
- Redact secrets/tokens from logs and UI.
- Never expose raw chat history to an admin panel unless explicitly authorized and required.
- High-impact actions require confirmation or a configured approval policy.

## 9. Frontend Architecture

### Suggested folder structure
```text
src/
  app/
    App.tsx
    routes.tsx
    providers/
      QueryProvider.tsx
      SocketProvider.tsx
      ThemeProvider.tsx
  components/
    shell/
      AppHeader.tsx
      DesktopLayout.tsx
      Panel.tsx
      StatusBadge.tsx
    satellite/
      SatellitePanel.tsx
      MapCanvas.tsx
      MapToolbar.tsx
      HeadlineList.tsx
    assistant/
      AssistantCorePanel.tsx
      HologramScene.tsx
      AssistantStateLabel.tsx
      TerminateButton.tsx
      MicrophoneButton.tsx
    modules/
      ModuleConnectorStack.tsx
      ModuleCard.tsx
    visual-hub/
      VisualHubPanel.tsx
      VisualPromptSuggestions.tsx
      VisualHistoryStrip.tsx
      VisualScene.tsx
    right-panel/
      RightWorkspace.tsx
      VoiceTab.tsx
      AgentTab.tsx
      NotesTab.tsx
      MessageComposer.tsx
  features/
    memory/
    skills/
    character/
    settings/
    permissions/
    notifications/
  hooks/
    useAssistantState.ts
    useWebSocket.ts
    useVoiceSession.ts
    useTaskEvents.ts
  services/
    apiClient.ts
    socketClient.ts
    permissions.ts
  state/
    appStore.ts
    assistantStore.ts
    chatStore.ts
  styles/
    tokens.css
    globals.css
  types/
    api.ts
    events.ts
    domain.ts
  tests/
```

### Frontend rules
- Strict TypeScript; avoid `any` except documented boundary cases.
- Separate presentational components from data access and side effects.
- Use a query/cache library for HTTP data and a small predictable store for UI/session state; do not duplicate server state in multiple stores.
- Runtime-validate API/WebSocket payloads with a schema library (e.g. Zod).
- Use a single WebSocket manager with reconnect, heartbeat, sequence/event IDs, and stale-state reconciliation.
- All backend calls pass through typed service modules.
- No business logic inside the Three.js render loop.
- Lazy-load heavy visual modules and dispose Three.js resources on unmount.
- Never put secrets in frontend environment variables or bundles.

## 10. Three.js / WebGL Requirements

- Central hologram may use particles, point clouds, line connections, shader effects, and a restrained glow.
- Use WebGL through Three.js; provide fallback content if WebGL is unavailable or GPU context is lost.
- Respect device pixel ratio but cap it to avoid excessive GPU usage.
- Handle resize, tab visibility, context loss/restoration, and component unmount.
- Use instancing/batched geometry where possible; avoid one mesh per particle if counts become large.
- Do not recreate geometry/materials on every React render.
- Provide an accessible textual state label alongside visual animation.
- Offer reduced-motion mode and a static low-performance fallback.
- Visual Hub’s layered diagram must be interactive only where interactions are defined; otherwise it is clearly illustrative.

## 11. Backend Integration and API Contract

The UI must integrate with the existing backend through a thin adapter layer. The following routes are a proposed contract, not a claim that they already exist. Map them to existing OpenClaw/Jarvis endpoints where possible; avoid duplicate APIs.

### Proposed HTTP endpoints
- `GET /api/v1/health` — app/backend health and capability flags.
- `GET /api/v1/app/config` — version, feature flags, allowed modes.
- `GET /api/v1/modules/status` — memory/skills/character/settings availability.
- `GET /api/v1/assistant/state` — authoritative assistant state.
- `POST /api/v1/assistant/sessions` — create voice/text session.
- `POST /api/v1/assistant/sessions/{session_id}/cancel` — cancel active session.
- `POST /api/v1/chat/messages` — submit a user message if HTTP submission is used.
- `GET /api/v1/chat/sessions/{session_id}/messages` — load conversation history.
- `GET /api/v1/tasks` — list tasks.
- `GET /api/v1/tasks/{task_id}` — task details.
- `POST /api/v1/tasks/{task_id}/cancel` — cancel task.
- `GET /api/v1/visual/history` — list visual hub history.
- `POST /api/v1/visual/tasks` — create visual task.
- `GET /api/v1/notes` / `POST /api/v1/notes` / `PATCH /api/v1/notes/{id}` / `DELETE /api/v1/notes/{id}` — notes only if persistence is enabled.
- `GET /api/v1/settings` / `PATCH /api/v1/settings` — supported settings.
- `GET /api/v1/permissions` — permission/capability state.

### Proposed WebSocket
- `GET /api/v1/events/ws` (or the existing configured socket path).
- Authenticate/authorize the socket; validate origin; use local-only binding by default.
- Event envelope:
```json
{
  "event_id": "uuid",
  "type": "assistant.state_changed",
  "timestamp": "2026-10-24T12:00:00Z",
  "correlation_id": "uuid",
  "sequence": 42,
  "payload": {}
}
```
- Required event types:
  - `connection.ready`
  - `connection.heartbeat`
  - `assistant.state_changed`
  - `assistant.transcript.partial`
  - `assistant.transcript.final`
  - `assistant.response.delta`
  - `assistant.response.completed`
  - `assistant.error`
  - `task.created`
  - `task.progress`
  - `task.awaiting_approval`
  - `task.completed`
  - `task.failed`
  - `task.cancelled`
  - `module.status_changed`
  - `visual.task.updated`
  - `permission.required`
  - `permission.changed`
  - `notification.created`

### WebSocket reliability rules
- Reconnect with exponential backoff and jitter.
- Send heartbeat/ping and detect stale connections.
- Deduplicate by `event_id`; reject/out-of-order handling by `sequence` where applicable.
- On reconnect, fetch authoritative state and recent events; do not assume no events were missed.
- Show “Reconnecting” or “Offline” status and stale-data timestamp.
- Do not retry unsafe actions automatically unless idempotency is guaranteed.

### Example assistant state payload
```json
{
  "session_id": "session-123",
  "state": "listening",
  "since": "2026-10-24T12:00:00Z",
  "can_cancel": true,
  "input_mode": "voice",
  "message": "Jarvis is listening"
}
```

### Example task payload
```json
{
  "task_id": "task-123",
  "status": "running",
  "title": "Analyze current screen",
  "current_step": "Inspecting visible window",
  "progress": null,
  "can_cancel": true,
  "requires_approval": false
}
```
Use `progress: null` when the backend cannot provide a defensible percentage.

## 12. Security and Trust Boundaries

- Bind local backend to loopback by default; do not expose it to the LAN without explicit configuration.
- Protect state-changing endpoints against unauthorized requests and CSRF-like cross-origin abuse.
- Use an ephemeral local auth token or an equivalent established mechanism; do not hard-code credentials.
- Validate WebSocket origin and every message payload.
- Treat model output, tool output, filenames, headlines, URLs, and web content as untrusted data.
- Sanitize rendered markdown/HTML; disallow arbitrary script execution in chat output.
- Allowlist attachment types and cap file size.
- Restrict file/system operations to approved backend tools and permissions.
- Confirm sensitive actions (deleting files, changing security settings, executing commands, external sending) according to policy.
- Never let a UI-only permission toggle grant an OS permission; call the actual permission API.
- Store secrets in OS-protected storage where available.
- Provide a privacy indicator and a visible way to stop capture.
- Keep an audit record of high-impact actions without logging secret content.

## 13. Performance Requirements

- First usable dashboard render target: ≤ 3 seconds on the project’s reference development machine, excluding slow backend startup.
- UI interaction response target: ≤ 100 ms for local navigation and button feedback.
- WebSocket event-to-visible-state target: ≤ 250 ms on a healthy local connection, excluding backend/model processing.
- Keep 3D animation near 60 FPS on capable hardware; degrade gracefully on weaker GPUs.
- Avoid blocking the UI thread with model work, filesystem scans, or large payload parsing.
- Virtualize long message/activity lists when necessary.
- Cap particle count and rendering resolution based on device performance.
- Measure startup, memory use, FPS, reconnect behavior, and large chat performance.

## 14. Accessibility and Usability

- All actions accessible by keyboard; visible focus ring.
- Semantic buttons and tab controls with correct roles/labels.
- Sufficient contrast; never rely on color alone for state.
- Tooltips for icon-only actions.
- Reduced-motion setting and OS preference support.
- Scalable text and correct behavior at common display scaling settings.
- Screen-reader text for assistant state and live updates, with excessive announcements throttled.
- Clear empty, loading, error, offline, permission-denied, and disabled states.
- Destructive actions require clear labels and appropriate confirmation.

## 15. Data and State Ownership

- Backend owns assistant/session/task/module truth.
- Frontend owns transient UI state: selected tab, open panels, composer draft, theme, and local presentation preferences.
- Persist only intended user data; define retention and deletion behavior for notes, history, transcripts, and visual outputs.
- Do not persist microphone/camera/screen data by default.
- If local cache is used, mark stale data and reconcile after reconnect.
- Use stable IDs for sessions, messages, tasks, notes, and history records.
- Every async action must be associated with a request/correlation ID to prevent response mix-ups.

## 16. Error and Edge Case Matrix

Test at least:
- Backend is not running on app launch.
- Backend starts after UI launch.
- WebSocket disconnects during a streaming response.
- Duplicate/out-of-order WebSocket events.
- User presses terminate repeatedly.
- Microphone permission denied or device missing.
- Camera/screen capture not supported by current shell.
- WebGL disabled or GPU context lost.
- Visual task returns unsupported content.
- Long assistant response and very long headline/title.
- Empty notes/history.
- Invalid attachment or oversized file.
- User switches tabs while a task is running.
- User closes the app while a task is active.
- Window resized to minimum supported dimensions.
- OS display scaling 125% and 150%.
- API returns malformed/unexpected data.
- Session expires or local auth token is invalid.
- User requests a high-impact action that requires approval.
- Reduced-motion mode enabled.

## 17. Testing Strategy

### Unit tests
- State machine transitions.
- API client error mapping.
- WebSocket event parsing, deduplication, ordering, reconnect.
- Permission and capability mapping.
- Chat composer key behavior.
- Module status mapping.
- Cancellation flow.

### Component tests
- Header actions and theme menu.
- Module cards and status indicators.
- Voice/Agent/Notes tabs preserve state.
- Visual Hub suggestions and history strip.
- Empty/loading/error/offline states.
- Accessibility labels and keyboard navigation.

### Integration tests
- UI connects to a test FastAPI backend.
- Real WebSocket events update the correct panels.
- Voice state transitions reflect backend events.
- Task create/cancel/completion flow.
- Notes/history persistence where enabled.
- Reconnect reconciles authoritative state.

### End-to-end tests
- Launch desktop app.
- Send text message and receive streamed response from a test backend.
- Start/stop voice session with mocked or real configured voice service.
- Open module views.
- Trigger visual task and observe task states.
- Disconnect/restart backend and recover.
- Verify permission-denied and unavailable states.
- Verify no fake success when a backend operation fails.

### Visual regression
- Capture screenshots at 1536×864, 1920×1080, and 1366×768.
- Compare panel geometry, spacing, borders, typography, and colors to the reference.
- Use an agreed tolerance for rendering/font differences; do not require pixel identity across different OS font rasterizers.
- Ensure all labels are live text, not baked into a screenshot.

## 18. Definition of Done / Acceptance Criteria

The build is accepted only when:
1. The dashboard layout matches the supplied reference hierarchy and proportions at target desktop sizes.
2. All required labels are correctly spelled and readable: SAT-LINK FEED, SATELLITE STREAM, TODAY HEADLINES, MEMORY, SKILLS, CHARACTER, SETTINGS, VISUAL HUB, VOICE, AGENT, NOTES, SYSTEM READY, and relevant state labels.
3. The main assistant panel displays the correct state based on backend events.
4. Terminate cancels the correct active task/session and displays backend acknowledgement or an error.
5. Memory, Skills, Character, and Settings cards open working views or truthful setup/unavailable states.
6. Voice/Agent/Notes tabs work and preserve independent state.
7. WebSocket disconnect/reconnect works and the UI reconciles missed state.
8. The Visual Hub prompt suggestions work; history is real or an honest empty state.
9. Map/headlines are real data or clearly labelled demo/unavailable content.
10. No visible button is dead; every icon-only action has a tooltip and accessible name.
11. UI remains usable when backend, microphone, camera, screen capture, or WebGL is unavailable.
12. Unit, integration, E2E, accessibility smoke, and visual regression tests pass.
13. No secrets are bundled in frontend code; sensitive operations require proper authorization.
14. No fake live status, fabricated progress, or false “listening” state appears in production mode.
15. The codebase is modular and follows the specified project structure or documents justified deviations.

## 19. Implementation Phases

### Phase 0 — Repository and architecture audit
- Inspect current Jarvis/OpenClaw repository, shell, API, state/events, voice, screen/camera, permissions, and existing components.
- Identify existing functionality and gaps.
- Produce a short architecture decision record before adding a new desktop shell.
- Do not overwrite working modules or create a parallel backend.

### Phase 1 — Design system and static layout
- Implement tokens, typography, panel grid, header, left feed, module connectors, assistant frame, Visual Hub frame, right workspace.
- Use fixture data only in an explicit development/demo mode.
- Compare screenshots against reference and tune geometry.

### Phase 2 — Backend adapter and live state
- Implement typed API client, WebSocket manager, event schemas, health status, reconnect and state reconciliation.
- Connect assistant/module/task states to real backend data.

### Phase 3 — Voice, chat, and task lifecycle
- Connect message submission, streaming output, voice capture/session state, cancellation, errors, and approval flow.
- Add tests for interruption and reconnect.

### Phase 4 — Visual Hub and Three.js
- Build performant hologram and diagram scenes.
- Connect prompt tasks and history to backend.
- Add WebGL fallback and reduced-motion support.

### Phase 5 — Modules and preferences
- Implement Memory, Skills, Character, Settings views and real capability flags.
- Add local preference persistence and permission UI.

### Phase 6 — Hardening and release
- Run visual, functional, accessibility, security, and performance checks.
- Package for target OS.
- Provide build/run instructions, environment template, logs/diagnostics, and a feature support matrix.

## 20. Required Deliverables from the AI Coding Agent

The coding agent must return:
1. A repository audit and architecture decision note.
2. A working desktop UI, not only a design or static mockup.
3. The agreed frontend and backend integration code.
4. Typed API and WebSocket contracts.
5. Environment example with no secrets.
6. Automated unit, integration, and end-to-end tests.
7. A setup/run/build README.
8. A feature matrix marking each feature `implemented`, `partially implemented`, `blocked`, or `not configured`.
9. Screenshots of the running UI at target sizes.
10. A list of assumptions, gaps, and any deviation from this PRD.
11. No claim of full functionality unless each relevant acceptance criterion has been tested.

## 21. Instructions to the AI Coding Agent

Use the attached reference screenshot as the visual source of truth and this PRD as the behavioral/architecture source of truth. First audit the existing repository. Preserve working Python/OpenClaw functionality. Do not start by replacing the backend or introducing a second desktop shell. Implement in phases and keep the app runnable at each phase.

Do not create dead buttons, hard-coded live states, fake data presented as real, fabricated progress, or placeholder integrations described as complete. If a required service is absent, implement the integration boundary, display a truthful unavailable/configuration state, and document exactly what is needed to complete it.

Use React + TypeScript + Tailwind CSS for the UI; Three.js/WebGL for the hologram and visual scenes; Python + FastAPI + WebSockets for backend communication; and PySide6 + Qt WebEngine only if the repository audit confirms it is the appropriate desktop host. Keep the code typed, modular, tested, accessible, secure, and performant.

## Appendix A — Visible Reference Copy

The screenshot visibly contains these major labels and elements:
- Product/header: Stonic AI, Feedback, Manage Billing, Support, version, Awareness, Theme, Profile.
- Left feed: SAT-LINK FEED, SATELLITE STREAM, EXPAND, 2D, 3D, Today, Map, Search, Alerts, More, TODAY HEADLINES.
- Connected modules: MEMORY, SKILLS, CHARACTER, SETTING/SETTINGS.
- Central panel: mode selector, holographic assistant, “Jarvis is listening”, TERMINATE, microphone control.
- Visual panel: VISUAL HUB, READY, visual hub, gesture, “What do you want to see?”, four example prompts, library/history strip.
- Right panel: VOICE, AGENT, NOTES, SYSTEM READY, greeting, voice input composer.

**Branding note:** the reference screenshot says “Stonic AI” in several places, while the requested product is Jarvis. The implementation should use one consistent product name chosen by the owner. Do not mix names accidentally.

## Appendix B — Suggested Environment Variables

```text
JARVIS_API_BASE_URL=http://127.0.0.1:<configured-port>
JARVIS_WS_URL=ws://127.0.0.1:<configured-port>/api/v1/events/ws
JARVIS_ENV=development
JARVIS_ENABLE_DEMO_DATA=false
JARVIS_LOG_LEVEL=INFO
```

Ports, auth strategy, and exact paths must be derived from the repository audit. Never assume these example values match the existing backend.

## Appendix C — Architecture Decision Reminder

The selected UI stack does not by itself make screen sharing, live camera, voice, computer control, or multi-agent execution functional. Each capability needs a real backend implementation, permissions, event contracts, failure handling, and tests. The UI must expose capability status and not conceal missing integrations.
