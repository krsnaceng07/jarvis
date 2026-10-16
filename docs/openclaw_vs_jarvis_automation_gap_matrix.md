# OpenClaw vs. JARVIS Automation Gap Matrix

**Reference System:** OpenClaw 2026.9.2  
**Target System:** JARVIS Architecture  
**Scope:** Automation, Messaging, WhatsApp, Desktop/Host Control, Safety, and Extensibility  

---

## 1. Architectural Dimension Comparison Matrix

| Architectural Dimension | OpenClaw 2026.9.2 Canonical Pattern | Current JARVIS State | Required Target State for Full Parity |
|:---|:---|:---|:---|
| **1. Extension Packaging** | Modular extension in `extensions/<id>/` with `openclaw.plugin.json` declaring contracts, skills, and tools. | `extensions/whatsapp` existed as a Phase 5.15 stub without tool or skill bindings. | Update `extensions/whatsapp/jarvis.plugin.json` with full tool contracts (`whatsapp_*`), declarative skills, and provider configs. |
| **2. Skill Declaration** | Declarative Markdown in `extensions/<id>/skills/<skill>/SKILL.md` with YAML frontmatter. | 58 skills exist in `skills/`, but no WhatsApp skill exists anywhere in JARVIS. | Create `extensions/whatsapp/skills/whatsapp/SKILL.md` and symlink/mirror in `skills/whatsapp/SKILL.md`. |
| **3. Provider Abstraction** | Provider abstraction separating channel/protocol logic from execution engines (`wacli`, `whatsmeow`, etc.). | Monolithic desktop adapter directly driving win32 keystrokes; no provider interface. | Introduce `MessagingProvider` base contract with `WhatsAppDesktopProvider` and `WhatsAppWebProvider` implementations. |
| **4. Tool Registry & Schemas** | Granular typed tools (`whatsapp_call`, `whatsapp_login`, etc.) with TypeBox/JSON-schema validation. | Monolithic `desktop` tool accepting loose dictionary arguments; prone to model guessing (`generic`). | Register dedicated granular tools (`whatsapp_send`, `whatsapp_open`, `whatsapp_search`, `whatsapp_state`) with strict Pydantic/JSON schemas. |
| **5. Recipient Safety Gate** | Multi-step recipient normalization (E.164 / JID), exact candidate evaluation, self-message prevention. | Simple substring match; lacked candidate disambiguation prompt before typing. | Implement full `RecipientGuard`: search, list candidates, require user disambiguation if ambiguous, match chat header before send. |
| **6. Window & Session Awareness** | Process-level session DB with concurrency lock (`activeCallAccounts`) and status tracking. | Windows API calls didn't verify foreground state or unminimize before typing. | Implement `ApplicationSessionManager` tracking PID, HWND, window state (normal, minimized, iconic), and active chat. |
| **7. Host Input Safety** | Zero blind keystroke dispatching. Strictly checks execution context before dispatch. | Blindly typed into active foreground window if WhatsApp was minimized. | Strict gate: If `not is_foreground()`, attempt restore. If still not foreground, abort immediately with explicit error. |
| **8. Observation Loop** | Pre/post-execution status query; asserts expected side-effects before reporting success. | Assumed success once `Enter` key was triggered. | Observe window title, verify composer content, assert delivery, and verify chat header. |
| **9. Task Continuity** | Multi-stage task state machine persisting stage progress across conversational turns. | Rudimentary task context without stage validation. | Structured `TaskContinuity` tracking Stage 1 (Resolve) through Stage 8 (Verify) with resume support. |
| **10. Truthfulness & Reporting** | Strictly returns structured errors or `completed_verified`; never fabricates success. | Returned success even when keystrokes landed in IDE or terminal. | Report `completed_verified`, `blocked`, or `failed`; explicitly state when verification could not confirm send. |
| **11. Self-Healing & Recovery** | State-aware recovery: detect failure $\to$ classify $\to$ restore state $\to$ retry only if safe. | Model retried identical failed calls in a loop without recovery action. | Implement recovery engine: unminimize, restart instance via URI protocol, refocus window, or clear stuck search box. |
| **12. Multi-App Extensibility** | Common plugin API and tool registration reusable for any service. | Custom one-off logic for WhatsApp in desktop runtime. | Unified `DesktopAutomationProvider` and `MessagingProvider` extensible to Telegram, Discord, Slack, etc. |

---

## 2. Priority Gaps to Close in Phase 3–11

1. **Gap 1 (Lifecycle)**: Wire `extensions/whatsapp` into JARVIS runtime plugin discovery and tool registration.
2. **Gap 2 (Provider & Adapter)**: Refactor `WhatsAppDesktopAdapter` into a formal `WhatsAppDesktopProvider` adhering to `MessagingProvider`.
3. **Gap 3 (Granular Tools)**: Replace ambiguous `desktop(action='generic')` with granular, schema-backed tools (`whatsapp_send_message`, `whatsapp_search_contact`, `whatsapp_open_chat`, `whatsapp_get_state`).
4. **Gap 4 (Zero Blind Typing)**: Guarantee that neither keystrokes nor clipboard contents can be dispatched unless the target window HWND is proven to be the active foreground window.
5. **Gap 5 (Observability & Verification)**: Validate that the active window matches the target app and that the message was submitted before declaring task fulfillment.
