# JARVIS Current Automation & Application Context Audit

## 1. Executive Summary

This document audits the current state of browser automation, application context awareness, and task continuity in **JARVIS** (`E:/jarvis`), contrasting current capabilities against real-world production requirements.

While JARVIS has successfully achieved foundational browser execution parity (Playwright integration, Chromium/Edge executable resolution, persistent context, 24-action schema, and inline page snapshot feedback), several critical architectural gaps remain when handling multi-turn, interactive web applications like YouTube.

---

## 2. Current Architecture & Components

### 2.1 Browser Runtime & Tooling
- **Source Files**:
  - `extensions/browser/src/browser_runtime.py`
  - `extensions/browser/src/browser_tool.py`
  - `extensions/browser/src/browser_tool_schema.py`
- **Current Capabilities**:
  - Supports Playwright persistent context with Chromium/Edge auto-detection and disk space protection.
  - Exposes 24 atomic OpenClaw-compatible actions: `tabs`, `open`, `close`, `focus`, `navigate`, `snapshot`, `screenshot`, `act`, etc.
  - Implements basic domain-level tab reuse: `open_tab()` checks existing tabs for matching hostname (e.g. `youtube.com`).
  - Implements inline page state attachment on `open` and `navigate` (`appendNavigatedPageState`), providing page text up to 2000 chars.

### 2.2 Task State & Memory Tracking
- **Source Files**:
  - `src/agents/task/task_state.py`: `TaskStateManager`, `TaskState`, `TaskStep`, `ExecutionRecord`.
  - `apps/desktop/src/jarvis_desktop/tool_pipeline.py`: `ToolSchemaRegistry`, `is_batch_parallelizable`.
  - `apps/desktop/src/jarvis_desktop/memory_bridge.py`: SQLite-backed facts and session memory.
- **Current Capabilities**:
  - Tracks discrete goal-oriented multi-step tasks across turns (`set_task_goal`).
  - Records tool execution history (`ExecutionRecord`) with verification outcomes and affected file paths.
  - Injects recent execution history and task progress into system prompt.

---

## 3. Identified Deficiencies & Failure Modes

### 3.1 Unconditional Reload on Domain Match
In `browser_runtime.py` lines 536-541:
```python
if tab.page.url != url:
    await tab.page.goto(
        url,
        wait_until="domcontentloaded",
        timeout=self.resolved.actionTimeoutMs,
    )
```
When a user says:
- Turn 1: *"Open YouTube"* $\rightarrow$ Opens `https://www.youtube.com`.
- Turn 2: *"Search Believer and play it"* $\rightarrow$ If the model attempts `open_tab("https://www.youtube.com")`, the runtime unconditionally calls `goto()`, reloading the homepage and erasing any ongoing search or playback state.

### 3.2 Lack of Application-Level Context & Pronoun Blindness
- JARVIS currently treats the browser as a generic DOM inspector with no semantic awareness of web applications (YouTube, Spotify, GitHub, Google Docs).
- **Pronoun Ambiguity**: When the user utters anaphoric commands such as *"play it"*, *"pause"*, *"resume"*, *"skip the ad"*, or *"turn up the volume"*, JARVIS lacks an application context resolver. The Decision Engine evaluates the prompt in a vacuum without knowing:
  1. What application is currently in the foreground / active tab?
  2. Is a video or audio stream currently playing or paused?
  3. What is the current media title, duration, and playback position?

### 3.3 Missing State Machine for Multi-Turn Web Workflows
Complex interactions require multi-step state transitions:
$$\text{HOME} \xrightarrow{\text{type search}} \text{SEARCHING} \xrightarrow{\text{press Enter}} \text{SEARCH\_RESULTS} \xrightarrow{\text{click video}} \text{WATCH\_PAGE} \xrightarrow{\text{handle ad}} \text{PLAYING}$$
Without a state machine:
- The LLM must discover the entire workflow dynamically on each turn.
- A single missing ref or transient loading state leads to tool execution loops or incorrect actions.

### 3.4 Absence of Real Playback Verification
- When an action like `click` is executed on a YouTube video card, JARVIS currently returns `{"ok": True}` if the click event was dispatched.
- **Problem**: This violates the OpenClaw mutation contract: action evidence alone does not prove goal completion. The click might hit an ad overlay, a cookie consent banner, or trigger navigation to an unrelated recommendation.
- JARVIS lacks domain-specific verification that inspects HTML5 `<video>` properties (`paused == false`, `currentTime > 0`, `readyState >= 3`).

### 3.5 Interstitial and Modal Vulnerability
- YouTube frequently presents blocking modals:
  - Google Cookie Consent (*"Before you continue to YouTube"*)
  - YouTube Premium promotional dialogs (*"Try YouTube Premium for 1 month free"*)
  - Video pre-roll and mid-roll advertisements (*"Video will play after ads"*, *"Skip Ad"*)
- JARVIS has no automated interstitial detection or auto-recovery handlers, causing automation to stall.

---

## 4. Architectural Summary & Mandate

To achieve complete OpenClaw parity, JARVIS requires an **Application Automation Runtime** (`src/application_automation/`) that:
1. Maintains an **Active Tab & Application Tracker** with session affinity.
2. Implements a **Contextual Pronoun Resolver** mapping *"play it"*, *"pause"*, etc., to the active application.
3. Provides a dedicated, robust **YouTube Application Adapter** with state machine, multi-tier locators, action handlers, playback verifier, and interstitial recovery.
