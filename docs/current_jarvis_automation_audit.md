# Current JARVIS Automation & WhatsApp Audit

**Target Workspace:** `e:/jarvis/`  
**Date:** September 2026  
**Auditor:** Principal AI Agent Systems & Reliability Architect  

---

## 1. Executive Summary

A comprehensive audit of the current JARVIS repository reveals a mixed state:
1. **Strong Core SDK & Extension Foundation**: JARVIS possesses a complete, OpenClaw-parity `packages/plugin_sdk` with plugin manifests, lifecycles, and tool registration APIs.
2. **Phase 5.15 Stub in `extensions/whatsapp/`**: The official channel plugin at `extensions/whatsapp/plugin.py` was merely a stub returning `Result.err("channel_stub")`, leaving messaging requests unhandled by the channel framework.
3. **Disconnected Desktop Automation Layer**: In response to user requests, a desktop automation layer was introduced under `src/desktop_automation/applications/whatsapp.py`. While functional for basic scenarios, it was partially decoupled from the OpenClaw plugin lifecycle, relying on monolithic shortcuts in `tool_pipeline.py`.
4. **The Minimized Window & Blind Typing Bug**:
   - `WindowDetector` previously returned internal 1x1 GDI+ helper windows (`GDI+ Window (WhatsApp.Root.exe)`), causing `focus_window` to target an invisible dummy window while the true application window remained minimized at coordinates `(-32000, -32000)`.
   - `desktop_runtime.py` had a logic escape (`if not focused and not adapter.find_window():`) that allowed keystrokes to be sent even when the target application was not in the active foreground, causing blind typing into whatever window was active (e.g. IDE or terminal).
   - Monolithic tool calling in `app.py` allowed Gemini to guess `action: 'generic'` or loop calls when actions were not strictly granular.

---

## 2. Component-by-Component Audit

### 2.1 `extensions/whatsapp/` (Channel Extension)
- **Manifest (`jarvis.plugin.json`)**:
  - `id`: `"whatsapp"`, `kind`: `"channel"`.
  - Statically defined with basic config schema (`bot_token`, `polling_interval_sec`).
  - Lacks tool contract declarations (`"contracts": { "tools": [...] }`).
  - Lacks declarative skills path (`"skills": ["./skills"]`).
- **Implementation (`plugin.py`)**:
  - Defined `WhatsAppPlugin(ChannelPlugin)`.
  - `send()` and `listen()` were stubs (`"whatsapp channel send is a Phase 5.15 stub"`).
  - Did not integrate with `src/desktop_automation` or expose desktop/web provider options.

### 2.2 `src/desktop_automation/` (Application Automation Layer)
- **Core Runtime (`core/desktop_runtime.py`)**:
  - Manages application adapters via `DesktopRuntime`.
  - Previously allowed unfocused execution if any window existed. (Now patched to enforce strict foreground gating).
- **Application Adapters (`applications/base.py`, `whatsapp.py`)**:
  - `BaseDesktopApplicationAdapter`: Handles process detection, window search, and keyboard/mouse input.
  - `WhatsAppDesktopAdapter`: Implemented search, open chat, and send message via simulated keystrokes (`Ctrl+F`, clipboard paste, `Enter`).
  - **Defect**: Did not verify foreground window state immediately before keystroke dispatch; did not filter out auxiliary/dummy Win32 windows.
- **Discovery (`discovery/window_detector.py`, `window_manager.py`)**:
  - `WindowDetector`: Enumerates Win32 desktop windows. Included GDI+ and IME helper windows.
  - `WindowManager`: Employs `AttachThreadInput`, `ShowWindow(SW_RESTORE)`, and Alt-key foreground unlock to unminimize and activate windows.

### 2.3 `apps/desktop/src/jarvis_desktop/tool_pipeline.py` & `app.py`
- **Tool Pipeline**:
  - Dispatched desktop actions through a single monolithic `desktop` tool.
  - The model frequently supplied `action: "generic"` or redundant arguments because the schema was broad and ambiguous.
  - Lacked tool-call deduplication and strict task fulfillment flags.
- **Main App Loop (`app.py`)**:
  - Voice turn loop received tool calls and executed them through `_execute_tool`.
  - When a tool failed with `Application 'Generic Application' could not be brought to the foreground`, the model fell into a retry loop.

### 2.4 Declarative Skills (`skills/`)
- JARVIS has 58 declarative skills in `skills/` (`weather`, `github`, `taskflow`, `youtube-automation`, etc.).
- **Missing**: No declarative skill for WhatsApp (`skills/whatsapp/SKILL.md` or `extensions/whatsapp/skills/whatsapp/SKILL.md`). The LLM lacked explicit prompt guidance on WhatsApp capability boundaries, recipient disambiguation, and safety contracts.

---

## 3. Root Cause of Previous Failures

1. **Lack of Architecture Unification**: Automation was split between a stubbed channel extension (`extensions/whatsapp`) and an ad-hoc desktop adapter (`src/desktop_automation`), forcing the tool pipeline to invent bridging logic.
2. **Blind Input Dispatch**: Automation executed keyboard shortcuts without verifying that `user32.GetForegroundWindow()` matched the intended target application.
3. **Ambiguous Tool Schemas**: Exposing a single `desktop` tool with dozens of untyped actions invited model hallucination (`action: 'generic'`).
4. **Missing Observability & Verification**: Completion was assumed upon sending `Enter` without confirming that the message actually posted or that the window was restored.
