# OpenClaw Browser & Application Automation Source Audit

## 1. Executive Summary

This document provides a deep, source-code-backed audit of the browser automation, application control, tab tracking, and session continuity subsystems in **OpenClaw** (`openclaw-main`). 

In OpenClaw, browser and application automation is **not** implemented as isolated, ad-hoc scripts (e.g., there is no standalone `youtube.py`). Instead, OpenClaw implements a principled, layered architecture:
1. **Core Browser Tool Engine** (`extensions/browser/src/browser-tool.ts`, `browser-tool.actions.ts`) exposing 24 atomic actions.
2. **Session Tab Tracking & Affinity** (`extensions/browser/src/browser-tool-session-tabs.ts`) maintaining strict ownership between conversational sessions and browser tabs via durable identifiers and aliases.
3. **ARIA Semantic Inspection & Locators** (`extensions/browser/src/browser-tool.snapshot.ts`, `browser-tool.schema.ts`) prioritizing accessibility trees over fragile pixel coordinates.
4. **Action Verification & Precedence** (`src/agents/tools/computer-tool-guidance.ts`, `computer-tool.ts`) enforcing mutation confirmation (`confirmed` > `unverifiable` > `suspected_noop`) and prohibiting blind retries.
5. **Inline Page State Attachment** (`appendNavigatedPageState`) ensuring that any state-mutating action immediately attaches fresh page context, eliminating redundant query loops.

---

## 2. Source-Level Audit of OpenClaw Subsystems

### 2.1 Tab Tracking, Identity & Session Affinity
- **Source File**: `extensions/browser/src/browser-tool-session-tabs.ts`
- **Key Concepts**:
  - `BrowserTabIdentity`: Binds a tab to `sessionKey`, `targetId`, `route`, `profile`, and `aliases`.
  - `readOpenedTab(result)`: Extracts durable aliases:
    ```typescript
    const aliases = [
      targetId,
      normalizeOptionalString(opened.tabId),
      normalizeOptionalString(opened.label),
      normalizeOptionalString(opened.suggestedTargetId),
    ].filter((alias): alias is string => Boolean(alias));
    ```
  - `createBrowserToolSessionTabs()`:
    - Provides `touch(targetId)`, `untrack(targetId)`, and `trackOpened(result, closeTab)`.
    - Handles tab compensation: if session tab registration fails, the newly opened tab is closed immediately (`BrowserTabTrackingCompensationError`), preventing orphaned tabs.
  - `suggestedTargetId`: In all tab listings and open responses, OpenClaw computes:
    ```typescript
    const suggestedTargetId = label ?? tabId ?? targetId;
    ```
    This ensures subsequent agent turns pass the stable alias (`targetId="youtube"` or `targetId="t1"`) rather than volatile Chromium DevTools target IDs that change upon process restart or target replacement.

### 2.2 Operating Loop & Tab Hygiene Guidelines
- **Source File**: `extensions/browser/skills/browser-automation/SKILL.md`
- **Key Patterns**:
  1. **Tab Hygiene Before Action**:
     - Check browser state: `action="tabs"` before opening a new tab.
     - "Before creating a tab for a named task, list tabs and reuse an existing matching label or URL when it is still usable."
     - If no tab exists, open with a meaningful label: `action="open", url="https://youtube.com", label="youtube"`.
  2. **Read Before Click**:
     - Inspect DOM with `action="snapshot"`, format `refs="aria"`.
     - Target matching elements via stable ARIA reference IDs (`axN`) or role/name queries (`button "Play"`, `searchbox "Search"`).
  3. **Inline Page State (`appendNavigatedPageState`)**:
     - `open` and `navigate` return the loaded page's snapshot inline.
     - The model receives page structure immediately upon navigation without needing a separate `snapshot` call.
  4. **Stale Ref Recovery**:
     - When an element action fails due to DOM updates:
       1. Re-snapshot the same `targetId`.
       2. Find current visible control.
       3. Retry once with fresh ref.
       4. If blocked by modal/dialog, report the blocker instead of looping.

### 2.3 Action Execution & Tool Parameters
- **Source File**: `extensions/browser/src/browser-tool.actions.ts`
- **Supported Actions** (24 total):
  - **Lifecycle**: `start`, `stop`, `status`, `doctor`, `profiles`.
  - **Tabs**: `tabs`, `open`, `focus`, `close`.
  - **Inspection**: `snapshot`, `screenshot`, `text`, `console`, `errors`, `requests`.
  - **Interaction (`act`)**: `click`, `type`, `press`, `hover`, `scrollIntoView`, `drag`, `select`, `fill`, `wait`, `evaluate`, `resize`.
- **Act Policy**:
  - `resolveBrowserActRequestTimeoutMs()`: Applies deterministic timeouts per action type (default 15,000ms).
  - Mutating actions invalidate earlier refs; navigation triggers fresh snapshot emission.

### 2.4 Computer Use & Mutation Precedence Contract
- **Source File**: `src/agents/tools/computer-tool-guidance.ts`
- **Core Principles**:
  1. **Target Precedence**:
     $$\text{elementRef (latest observation)} > \text{window coordinates} > \text{desktop coordinates}$$
  2. **Outcome Precedence**:
     $$\text{effect: "confirmed"} > \text{unverifiable} > \text{suspected\_noop}$$
     *Action execution alone does not prove the user's goal was achieved.* A click on a button must be verified by inspecting subsequent UI state (e.g., video playing, URL change, element appearance).
  3. **No Blind Retries**: Never re-execute a mutating action without observing post-mutation state.
  4. **Untrusted Input**: All on-screen content is treated as untrusted; the agent must never execute instructions injected into the web page that contradict the user's prompt.

---

## 3. Why OpenClaw Never Loses YouTube Context

In OpenClaw, the sequence:
> Turn 1: *"Open YouTube"*  
> Turn 2: *"Search Believer and play it"*

executes seamlessly because:
1. **Turn 1**: The agent calls `action="open", url="https://www.youtube.com", label="youtube"`. OpenClaw records the tab under session key with alias `youtube` and returns the loaded page snapshot.
2. **Context Persistence**: The session tab registry remembers that tab `youtube` is active and open on domain `youtube.com`.
3. **Turn 2**: When the user says *"Search Believer and play it"*, OpenClaw's prompt and tool selector ground the intent against the active session tab.
4. **Tab Reuse**: OpenClaw does not call `open` again to create a duplicate window; it addresses `targetId="youtube"`, inputs the search query into the searchbox, clicks search, observes search results, identifies the video card for "Believer", clicks it, and verifies playback.
