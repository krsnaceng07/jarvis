# JARVIS Browser Automation Architecture Audit

**Repository**: `E:/jarvis`  
**Date**: September 2026  
**Auditor**: Senior Autonomous-Agent Systems & Reliability Engineer  
**Objective**: Comprehensive Phase 2 architectural audit of JARVIS's browser automation, tool execution lifecycle, state management, and observed failure modes.

---

## 1. Inventory of Files & Responsibilities

| Subsystem / Capability | Responsible Files in JARVIS | Current Implementation Assessment |
| :--- | :--- | :--- |
| **Browser Tool Registration** | `extensions/browser/jarvis.plugin.json`<br>`extensions/browser/src/browser_tool.py`<br>`apps/desktop/src/jarvis_desktop/app.py:1270-1300` | Manifest exposes tool `browser`. Desktop registers it into Live session tools. |
| **Browser Action Schema** | `extensions/browser/src/browser_tool_schema.py` | Pydantic schema supporting 24 actions (tabs, open, close, act, snapshot, etc.). |
| **Browser Action Execution** | `extensions/browser/src/browser_tool.py:101-382`<br>`extensions/browser/src/browser_runtime.py:250-450` | Direct dispatch to Playwright locators. Returns `{ "ok": True }` upon driver event acceptance. |
| **Browser Snapshot / Observation** | `extensions/browser/src/browser_runtime.py:380-450` | Supports ARIA snapshot and plain text extraction. Lacks immutable `observation_id` tracking. |
| **Tab / Target Management** | `extensions/browser/src/browser_runtime.py:120-220`<br>`src/application_automation/active_tab_tracker.py` | `ActiveTabTracker` tracks tabs by URL, title, domain. Missing cross-lifecycle `TargetStaleError` recovery in general browser tool. |
| **Selector Handling & Resolution** | `extensions/browser/src/browser_runtime.py:510-580`<br>`src/application_automation/application_session_manager.py` | `_resolve_target()` attempts role/selector/text/coords. When selector is missing, Playwright raises `TimeoutError`. |
| **Tool Result Processing** | `apps/desktop/src/jarvis_desktop/app.py:1700-1850`<br>`apps/desktop/src/jarvis_desktop/tool_pipeline.py` | Validates schemas, captures output text. Does not enforce post-action state verification before returning result. |
| **Tool-Call Loop & Lifecycle** | `apps/desktop/src/jarvis_desktop/app.py:1697-1850` | Receives Gemini Live function calls and executes them sequentially. |
| **Task State Model** | `apps/desktop/src/jarvis_desktop/app.py` (fragmented flags)<br>`src/application_automation/application_session_manager.py` | No centralized `RuntimeState` machine. State is scattered across prompt history, `_last_user_turn`, and ephemeral vars. |
| **Active-Turn Validation** | `apps/desktop/src/jarvis_desktop/app.py:1705-1721` | Checks `if not current_user_speech:` and logs `Autonomous tool call suppressed`. Lacks explicit `turn_id` binding. |
| **Final Answer Generation** | `apps/desktop/src/jarvis_desktop/app.py:1600-1700` | Streamed directly from Gemini Live model based on tool execution string results. |
| **Success Detection** | Naive `res.get("ok")` in `browser_tool.py:88-91` | Treats driver delivery as task completion. Model hallucinates success without DOM proof. |
| **Retry Logic** | Implicit model loop on Playwright exception | When locator times out, model invents alternative CSS selectors and repeats failed clicks. |
| **Session Persistence** | `packages/agent_runtime/src/agent_runtime/session_store.py`<br>`src/application_automation/application_session_manager.py` | Persists session records to SQLite. |

---

## 2. Root-Cause Analysis of Observed Failures

### 2.1 Failure: Clicks Subscribe but does not verify; claims completion when action failed
- **Code Site**: `extensions/browser/src/browser_tool.py:319-335`
- **Root Cause**:
  When `act(kind="click", selector="...")` executes, Playwright executes `locator.click()`. If the locator is clicked, the tool returns:
  ```json
  { "ok": true }
  ```
  The desktop tool pipeline converts this to `"Browser action completed successfully."` and feeds it to the LLM. The LLM immediately announces: *"I have subscribed to the channel."* In reality, the click might have hit a non-interactive element, triggered a login prompt, or been dismissed by YouTube, with zero change in subscription state.
- **Missing Architecture**: OpenClaw's post-action verification engine enforcing:
  $$\text{effect: "confirmed"} > \text{unverifiable} > \text{suspected\_noop}$$

### 2.2 Failure: Does not check whether requested action is already completed
- **Code Site**: `extensions/browser/src/browser_tool.py:319-335`
- **Root Cause**:
  There is no pre-action state evaluation in `BrowserTool`. When the user asks *"Subscribe to MrBeast"*, if the user is already subscribed (button displays `"Subscribed"`), JARVIS blindly clicks the button again, which **unsubscribes** the user or opens an unsubscribe confirmation modal!
- **Missing Architecture**: Pre-action state check answering:
  - *Has this action already been completed?*
  - *What evidence proves it has or has not been completed?*
  If already complete, report `already_completed` with zero mutation clicks.

### 2.3 Failure: Uses invalid selectors and repeatedly retries failed selectors
- **Code Site**: `extensions/browser/src/browser_runtime.py:510-580`
- **Root Cause**:
  When the model issues `act(kind="click", selector="ytd-subscribe-button-renderer button")`, if YouTube has changed its DOM structure or the button is inside a shadow root, Playwright hangs until `Timeout 30000ms exceeded`.
  The exception is returned to the model as an error message. Because JARVIS does not supply fresh semantic element references (`axN`), the model starts guessing arbitrary CSS selectors (`div.subscribe`, `button#subscribe-button`, `a[aria-label='Subscribe']`), causing a cascading loop of timeouts.
- **Missing Architecture**: Observation-first element resolution:
  - Generate fresh snapshot with short-lived `observation_id` and semantic refs (`axN`).
  - Stale observation invalidation on navigation.
  - Strict retry budget: max 1 re-observation before graceful refusal.

### 2.4 Failure: Autonomous tool call suppressed: no user command in active turn
- **Code Site**: `apps/desktop/src/jarvis_desktop/app.py:1705-1721`
- **Root Cause**:
  Gemini Live model continues generating function calls after turn completion or when audio pauses. `app.py` has a reactive guard:
  ```python
  if not current_user_speech:
      print(f"[JARVIS] 🛑 Autonomous tool call '{fc.name}' suppressed: no user command in active turn.")
  ```
  However, this guard only checks if `current_user_speech` string is empty at that microsecond. It lacks an authoritative `active_user_turn_id` and `active_task_id` state machine. If a user previously spoke 2 seconds ago and the model delayed its call, it gets erroneously executed, or if the model emits a multi-step call, subsequent steps risk being suppressed or orphaned.
- **Missing Architecture**: Structured `turn_id` admission lifecycle matching OpenClaw's `prepareToolCall` and `beforeToolCall` AbortSignal.

### 2.5 Failure: Operates on wrong tab or duplicate queries in same tab
- **Code Site**: `extensions/browser/src/browser_tool.py:220-233`, `src/application_automation/active_tab_tracker.py`
- **Root Cause**:
  When the user says *"Search Tere Naam"*, then *"Now search another song"*, the browser tool does not inspect the active tab's domain and URL before acting. It either opens a redundant new tab or blindly injects navigation into whatever tab happens to be active (even if it's an unrelated document or Google login page).
- **Missing Architecture**: Explicit `TargetManager` enforcing domain/task association and `TargetStaleError` detection.

### 2.6 Failure: Attempts Google Login blindly without secure auth handling
- **Code Site**: `extensions/browser/src/browser_runtime.py`
- **Root Cause**:
  When YouTube redirects to Google sign-in (`accounts.google.com`), JARVIS does not detect the transition to an authentication boundary. It attempts to click or type into login inputs as if it were still navigating YouTube, risking password guessing or getting trapped by 2FA/passkeys/CAPTCHA.
- **Missing Architecture**: Structured `AuthState` detector (`auth_required`, `human_verification_required`, `auth_success_verified`) with zero secret logging.

---

## 3. Current JARVIS State Machine Deficiencies

JARVIS currently lacks an authoritative central state model. State is split between:
1. Model context memory (ephemeral, prone to hallucinations).
2. Desktop app instance attributes (`_last_user_turn`, `_turn_completed`).
3. `ApplicationSessionManager` (partial state for specialized adapters, bypassed by direct `browser` tool calls).

```
Current Fragmented Architecture:
[User Voice] ──> [Gemini Live] ──> [Desktop app.py] ──> [BrowserTool.execute] ──> [Playwright]
                     │                    │                      │                     │
               (Hallucinates       (Checks string         (Returns ok=true     (Times out or
                completion)         speech only)           blindly)             blind clicks)
```

To achieve OpenClaw parity, this must be unified into an **Authoritative Runtime State Machine** that governs all tool admissions, element resolutions, and verification gates.
