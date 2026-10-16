# OpenClaw vs JARVIS Automation Parity Matrix

## 1. Parity Matrix Overview

This matrix contrasts **OpenClaw** (`openclaw-main`) against **JARVIS** (`E:/jarvis`) across 12 architectural dimensions governing browser automation, application context, session continuity, and reliability.

| # | Dimension | OpenClaw Implementation | Current JARVIS Status | Parity Gap & Remediation Plan |
|---|---|---|---|---|
| **1** | **Tab Identity & Tracking** | `browser-tool-session-tabs.ts`: `BrowserTabIdentity`, `aliases`, `suggestedTargetId` (prefers `label` > `tabId` > `targetId`). | `browser_runtime.py`: Simple sequential integer ID `t1, t2`. Basic domain reuse. | **Partial**. Upgrade `browser_runtime.py` to support semantic labels, alias indexing, and safe tab reuse without forced reload. |
| **2** | **Session Affinity** | Binds tabs to `sessionKey`. Tracks `touched` tabs per turn; untracks on explicit close or compensation. | No session key binding; tabs are global to browser context. | **Gap**. Implement `SessionTabTracker` binding tabs to conversational sessions. |
| **3** | **Application Context Awareness** | Skill-level awareness + `get_window_state` accessibility tree observation. | Browser is purely generic DOM inspector. No awareness of active app type. | **Gap**. Create `src/application_automation/` with `ApplicationSessionManager` and app adapters. |
| **4** | **Contextual Pronoun Resolution** | Decision loop grounds "it", "this", "pause", "resume" against active session window / tab state. | LLM receives raw text; fails on anaphoric references without explicit target. | **Gap**. Implement `ContextualResolver` resolving pronouns against active media / application state. |
| **5** | **Element Targeting & Locators** | ARIA-first (`snapshotFormat="aria"`, `refs="aria"`). Roles + accessible names (`button "Play"`). | Basic CSS selector & coordinate support. ARIA snapshot text supported. | **Partial**. Provide multi-tier locator strategy: ARIA role/name $\rightarrow$ semantic attributes $\rightarrow$ CSS fallback $\rightarrow$ JS eval. |
| **6** | **Mutation Verification Precedence** | `computer-tool-guidance.ts`: `confirmed` > `unverifiable` > `suspected_noop`. Prohibits blind retry. | Returns `ok: True` if Playwright API call completes without error. No effect verification. | **Gap**. Implement `ActionVerifier` verifying DOM state changes and media playback (`paused == false`). |
| **7** | **Inline State Feedback** | `appendNavigatedPageState`: attaches compact snapshot to `open`, `navigate`, and mutating `act` results. | Implemented for `open` and `navigate` in PR 1B. Missing for mutating `act`. | **Partial**. Extend `appendNavigatedPageState` to high-level application actions. |
| **8** | **Application State Machine** | Dynamic ARIA inspection; skills enforce state transitions (home $\rightarrow$ search $\rightarrow$ results $\rightarrow$ act). | No formal state machine for web applications. | **Gap**. Implement formal `YouTubeStateMachine` (`HOME`, `SEARCH_RESULTS`, `VIDEO_PLAYING`, `AD_PLAYING`). |
| **9** | **Interstitial & Popup Handling** | Operating loop detects consent modals, permission prompts, and handles or reports blockers. | Modals block action execution; cause timeouts or incorrect element clicks. | **Gap**. Implement `YouTubeRecoveryHandler` for Google Consent, Premium popups, and Ad skipping. |
| **10** | **Execution Mode Precedence** | Background delivery mode first; escalates to foreground only if background fails or occluded. | Foreground execution only via Playwright browser context. | **Maintained**. Foreground browser automation is appropriate for user-facing desktop assistant. |
| **11** | **State & Memory Persistence** | SQLite-managed session records, tool transcripts, and durable profile metadata. | `TaskStateManager` + `ExecutionRecord` + SQLite facts. Lacks active application state. | **Partial**. Add `ApplicationMemoryRecord` to `TaskState` and session memory. |
| **12** | **Self-Healing & Error Recovery** | Stale ref recovery: snapshot again $\rightarrow$ find visible control $\rightarrow$ retry once. Honesty on blockers. | `RecoveryDecisionEngine` handles coding tools and provider fallbacks, but not browser DOM refs. | **Gap**. Add browser-specific self-healing: stale ref retry, re-snapshot, and selector fallback. |

---

## 2. Priority Remediation Roadmap

To achieve 100% parity on YouTube and application automation:
1. **Phase 1**: Implement `ApplicationSessionTracker` & `ActiveTabTracker` in `src/application_automation/`.
2. **Phase 2**: Implement `ContextualResolver` for pronoun and media control resolution.
3. **Phase 3**: Implement `YouTubeAdapter` with multi-tier locators, state machine, playback verifier, and ad/consent recovery.
4. **Phase 4**: Wire application automation into `extensions/browser/` and `DecisionEngine`.
5. **Phase 5**: Add comprehensive test suites verifying multi-turn flows, tab reuse, and recovery.
