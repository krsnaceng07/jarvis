
# JARVIS UI PRD Addendum — Implementation Lock & Fidelity Checklist
**Version:** 1.1 Addendum | **Date:** 24 October 2026  
**Use with:** `JARVIS_UI_PRD_Full_Functional_Specification.docx` and the original reference screenshot.

## Why this addendum exists

The main PRD defines the major layout and functionality. This addendum closes common gaps that cause coding agents to produce a visually similar mockup rather than a complete, faithful, tested application. Treat this addendum and the main PRD together as one specification.

## 1. Priority rules and source of truth

When instructions conflict, follow this order:
1. Existing working Jarvis/OpenClaw repository behavior and safety/security constraints.
2. Explicit product decisions from the owner in the conversation.
3. This addendum.
4. Main PRD.
5. Reference screenshot for visual appearance.
6. Agent assumptions (last resort; document them).

Do not blindly copy the screenshot's “Stonic AI” brand if the target product is Jarvis. Unless the owner says otherwise, use **JARVIS** consistently in the product name, voice composer, window title, settings, logs, and app metadata. Keep the reference's visual design, not its unrelated brand identity. Preserve requested module labels: **MEMORY, SKILLS, CHARACTER, SETTINGS**.

The original screenshot contains rasterized, tiny text that cannot be recovered with perfect certainty. Do not invent claims or make unreadable placeholder text. Use the visible labels explicitly listed here; where the screenshot is ambiguous, preserve the intended role and document the choice.

## 2. Visual-fidelity lock

### 2.1 Required screenshot targets
Capture and compare the running application at:
- 1656 × 936 — supplied screenshot's native dimensions (if the file available to the agent matches this size).
- 1536 × 864 — standard 16:9 target.
- 1920 × 1080 — high-resolution target.
- 1366 × 768 — compact laptop target.

The primary visual comparison must use the exact supplied reference image, not a newly generated substitute.

### 2.2 Layout geometry
Use relative proportions and CSS Grid/Flex rather than positioning every item absolutely. At the reference aspect ratio, aim for:
- Top bar: approximately 4–5% of screen height.
- Left feed/headlines rail: approximately 17–18% of content width.
- Middle workspace (module connectors, assistant hologram, Visual Hub): approximately 52–54% of content width.
- Right Voice/Agent/Notes panel: approximately 28–30% of content width.
- Main content begins below the top bar and fills the remaining height.
These are starting measurements, not hard-coded truth. Tune by screenshot overlay and report any justified deviations.

### 2.3 Required panel order
1. Full-width top bar.
2. Left rail: SAT-LINK FEED / SATELLITE STREAM / map / Today-Map-Search-Alerts-More navigation.
3. Left rail below map: TODAY HEADLINES list.
4. Middle-left connector cards in this exact order: MEMORY (cyan), SKILLS (green), CHARACTER (red), SETTINGS (cool blue/white).
5. Central hologram card: mode selector, particle/point-cloud head, real state label, TERMINATE, microphone.
6. Lower middle: VISUAL HUB header/status/tabs, layered diagram, prompt suggestions, library/history strip.
7. Right full-height workspace: VOICE / AGENT / NOTES tabs, body, bottom composer.
8. No screenshot framing, watermark, unrelated desktop/photo background, or decorative external UI around the application.

### 2.4 Visual design rules
- Canvas: very dark navy/near-black, subtle grid texture.
- Borders: thin cyan/teal; brighter only for selected/active states.
- Accent mapping: cyan = primary/active; green = healthy/connected; red = destructive/critical; cool blue/white = neutral/system.
- Corners: reference-inspired chamfered corners on hero panels; moderate rounded corners on ordinary cards.
- Keep glow restrained. Text readability outranks glow.
- Build all labels as real text, never as part of a background image.
- Use SVG/vector icons consistently; no emoji in the production interface.
- Match the reference hierarchy and density, but improve legibility rather than reproducing screenshot blur.
- Avoid generic template-card appearance. The overall silhouette, panel ratios, connector routes, and dense desktop layout must remain recognizable.

### 2.5 Required labels
- Product: JARVIS (unless owner explicitly selects another name).
- SAT-LINK FEED
- SATELLITE STREAM
- EXPAND
- 2D / 3D (only enable if both modes work)
- TODAY HEADLINES
- MEMORY
- SKILLS
- CHARACTER
- SETTINGS
- Assistant states such as SYSTEM READY, LISTENING, THINKING, SPEAKING, WORKING, WAITING FOR APPROVAL, OFFLINE, ERROR (show only the state that is true).
- TERMINATE
- VISUAL HUB
- READY / DISCONNECTED as truthful capability states
- VOICE / AGENT / NOTES
- Message composer placeholder: “Type to Jarvis…”
- Library/history strip

## 3. Explicit capability matrix — no fake functionality

Before implementation, the agent must create `docs/ui-capability-matrix.md` with columns:
`Feature | Existing backend capability | UI implemented | Integration tested | Permissions | Limitations | Status`.

For each feature, use only these statuses:
- `implemented-and-tested`
- `implemented-ui-only`
- `backend-missing`
- `blocked-by-permission`
- `not-in-scope`

Required rows:
- Text chat and streaming
- Voice capture/transcription/TTS
- Barge-in/interruption
- Screen capture/live screen observation
- Live camera capture
- Hologram state synchronization
- Memory list/search/update/delete (only capabilities supported by policy)
- Skills list/run/permissions/errors
- Character/persona/voice configuration
- Settings persistence
- Agent/task list/current step/approval/cancel
- Visual Hub prompt execution/output/history
- Satellite/map data provider
- Headlines data provider
- Notes persistence
- Desktop notifications
- Local file attachments
- Backend offline/reconnect
- Theme/window-size persistence

Never mark a row implemented-and-tested unless a test actually ran and passed. If the existing backend does not support a capability, do not fake it; define the adapter interface and mark it backend-missing.

## 4. Screen and camera requirements

The UI must not imply that the assistant sees the screen or camera just because a panel is visible.

### Screen observation
- Add an explicit screen observation control in the Visual Hub or a clearly discoverable toolbar location.
- States: unsupported, permission-needed, permission-denied, idle, capturing, paused, processing, result-ready, error.
- Show a visible capture indicator and the current capture target (window/display) when supported.
- Allow stop/pause; stop capture immediately when requested.
- Show the last successful observation time and whether the displayed preview is stale.
- If continuous streaming is supported, indicate frame cadence and connection status; do not show “live” if only one screenshot was captured.
- Require confirmation/permission before enabling ongoing observation, according to platform capabilities and the existing security policy.

### Live camera
- Add a camera source selector/preview only if the current desktop shell and backend support it.
- Request OS/browser permission explicitly; handle denied/no-device/in-use states.
- Show a visible camera-active indicator and Stop Camera control.
- Do not save frames by default; follow the app's privacy and retention policy.
- If camera support is not implemented, show “Camera integration not configured” rather than a fake stream.

### Cross-model behavior
The UI must be model-agnostic. Display the active model/provider and capabilities from backend configuration. Do not assume every model supports images, video, streaming, or tool use. When a model lacks a capability, show a clear explanation and disable only the unsupported action.

## 5. Agent and task lifecycle requirements

Represent task states explicitly:
`queued → running → waiting_for_approval / blocked → running → completed / failed / cancelled`.
Not all transitions are valid; the backend is authoritative.

Every task item should show, when available:
- Task title and stable ID in details view.
- State and current step.
- Started/updated time.
- Progress only if the backend reports meaningful progress.
- Tools being invoked, with safe summaries.
- Permission/approval requirement.
- Cancel action only when cancellation is supported.
- Final result or error and retry action only if retry is safe.

If the backend can run multiple agents/tasks concurrently, show separate task identities. Do not let one task's events overwrite another task's UI. Use correlation IDs and stable task IDs.

## 6. Voice and chat details

- Keep text chat usable when microphone permissions are denied.
- Distinguish microphone capture from speech transcription and assistant audio playback.
- Show transcript partial/final states separately if the backend exposes them.
- If TTS is playing, show SPEAKING; when interrupted, transition to the correct state.
- Do not automatically start microphone capture on application launch unless the owner has explicitly enabled this setting and the OS/platform permission policy permits it.
- Add Stop Speaking / interrupt control if the audio service supports it.
- Show reconnect/retry when streaming fails; do not silently duplicate a user message on retry.
- Preserve draft text when switching tabs or after a recoverable failure.
- Support copy response, retry response, and scroll-to-latest where applicable.
- For markdown output, sanitize HTML and render code blocks safely.

## 7. Accessibility, localization, and usability lock

- All actions must be keyboard operable.
- Focus must be visible.
- Provide accessible names for icon-only controls.
- Use text/icons as well as color to communicate states.
- Respect reduced motion and high contrast where possible.
- UI language must be configurable; don't mix English and Hindi/Nepali strings randomly.
- Avoid tiny labels that become unreadable at 125–150% OS scaling.
- Keep tab order logical: header → left navigation → module stack → assistant controls → Visual Hub → right panel/composer.
- Provide a first-run connection/setup view if the backend is not configured.

## 8. Data, loading, and failure-state specification

Every data-driven panel must have all applicable states:
- Initial loading/skeleton
- Loaded
- Empty/no records
- Stale data
- Refreshing
- Offline/disconnected
- Permission required/denied
- Backend capability unavailable
- Error with retry
- Partial result

No panel should be permanently blank with no explanation. No button should remain visually active when the action is unavailable. Disable with a short reason or show a setup action.

## 9. Desktop packaging and shell decision gate

Before adding PySide6 + Qt WebEngine:
1. Inspect repository and identify current shell/launch process.
2. Determine whether the existing OpenClaw setup already provides a desktop/webview layer.
3. Compare reuse vs replacement for screen capture, camera, audio, OS permissions, keyboard shortcuts, window controls, packaging, auto-start, and process lifecycle.
4. Write `docs/architecture-decisions/ADR-001-desktop-shell.md`.
5. Choose one desktop shell only. Do not run duplicate shells or duplicate backend processes.
6. Confirm that the selected shell can support the intended screen/camera/voice features on each target OS.
7. Keep Python as the core agent engine unless the repository owner explicitly approves a change.

If the existing shell is suitable, reuse it. If it is not, present the smallest justified migration plan before removing anything.

## 10. API and event contract additions

In addition to the main PRD's proposed contracts, the agent must map actual existing APIs and events in `docs/api-contract-map.md`. Each row must contain:
`UI action/state | HTTP route or event | request schema | response/event schema | auth/permission | cancellation behavior | error behavior | test`.

Minimum event behavior:
- All events have timestamp, event ID, and correlation/session/task ID as applicable.
- Task and session events must not be conflated.
- Streaming output has a defined sequence/chunk order.
- Backend errors use a stable error code and safe user-facing message.
- Reconnection triggers state reconciliation.
- Cancel/stop commands require backend acknowledgement.
- State-changing requests should use idempotency protection where duplicate execution would be harmful.

Do not implement every proposed endpoint as a new endpoint if the existing API already provides equivalent functionality. The adapter should map the frontend to the real backend.

## 11. Required repository documents

The coding agent must create or update:
- `docs/ui-capability-matrix.md`
- `docs/architecture-decisions/ADR-001-desktop-shell.md`
- `docs/api-contract-map.md`
- `docs/ui-state-machine.md`
- `docs/visual-regression.md`
- `docs/security-and-permissions.md`
- `docs/known-limitations.md`

These documents must reflect the actual code, not a future wish list.

## 12. Visual comparison workflow

1. Run the UI at the reference dimensions.
2. Capture a screenshot with no browser chrome or unrelated desktop content.
3. Overlay it with the reference at 50% opacity or use a pixel-difference tool.
4. Compare: overall column ratios, top bar height, left map size, module connector positions, hologram panel dimensions, Visual Hub height, right panel width, borders, typography, spacing, and label alignment.
5. Fix the largest geometric mismatches first; then colors, fonts, icons, and micro-spacing.
6. Repeat at all target resolutions and at 125%/150% OS scaling.
7. Save final screenshots and record remaining differences.
8. Do not claim “pixel-perfect” if visual comparison was not performed.

## 13. Definition of Done — stricter release gate

Do not call the build complete until all are true:
- [ ] Existing repository audited and shell decision recorded.
- [ ] Required panel hierarchy and module order match the reference.
- [ ] Product naming is consistent; modules read MEMORY, SKILLS, CHARACTER, SETTINGS.
- [ ] All controls have defined, tested behavior or are clearly unavailable.
- [ ] Backend state, voice, task lifecycle, and errors drive the UI.
- [ ] WebSocket reconnect and state reconciliation tested.
- [ ] Screen/camera capabilities are real, permissioned, and visibly indicated—or explicitly marked not configured.
- [ ] No fake satellite/news/live data in production mode.
- [ ] Three.js scene resizes, cleans up resources, and has fallback behavior.
- [ ] Layout tested at all required sizes and OS scaling settings.
- [ ] Accessibility smoke tests pass.
- [ ] Unit, integration, E2E, and visual comparison results are recorded.
- [ ] Capability matrix accurately identifies unimplemented backend features.
- [ ] README explains setup, run, test, build, and troubleshooting.
- [ ] No secrets or unsafe permission bypasses.
- [ ] Agent reports all incomplete work honestly.

## 14. Final instruction to the coding agent

Build from the actual repository, not from assumptions. Read both PRD files and the original screenshot first. Preserve working features. Make a short plan, inspect the existing shell and backend, and implement in small verifiable phases. Match the screenshot's layout and styling closely, but do not turn the screenshot into a background image. All text and controls must be real UI elements.

The expected result is a running, testable desktop application with real integrations where available—not a Figma-like mockup, not a static HTML page, and not a dashboard with decorative buttons. Where the repository lacks a backend capability, document the exact missing service/API/permission and show an honest unavailable state. Do not claim “fully functional” without evidence from tests.
