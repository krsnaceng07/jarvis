# JARVIS Runtime Architecture & Operational Audit

**Auditor:** Principal AI Agent & Systems Architect  
**Scope:** `e:/jarvis` (Desktop HUD, Agent Runtime, Tool Pipeline, Verification Layer)  
**Objective:** Identify specific root causes of real-time hallucinations, volume errors, desktop unreliability, amnesia, and missing execution stages in prior JARVIS iterations.

---

## 1. Identified Runtime Defects & Root Causes

### 1.1 Problem A: Incorrect Real-Time Information (Date, Time, Timezone, System Metrics, Weather, News)
- **Observed Defect**: When asked "What time is it?" or "What's today's date?", JARVIS relied on static prompt snapshots taken at process launch or model hallucination based on pre-training cutoff.
- **Root Cause**: Prior to this redesign, JARVIS did not inject live microsecond timestamps into active conversational turns. There was no dedicated `LiveClock` module or system info tool accessible to the Gemini Live session.
- **Correction**: Built `src/system/live_clock.py` (querying host system clock and IANA timezone), `src/system/system_metrics.py` (CPU, RAM, disk, battery, network via `psutil`), and `src/system/web_search_provider.py` (DuckDuckGo real-time search). Injected delimited `## Temporal Context` into turns via `build_turn_prompt_context()`.

### 1.2 Problem B: Desktop Automation Unreliability (Focus, App Launch, UI Actions)
- **Observed Defect**: Opening applications resulted in duplicate windows, focus stealing failures, or reporting success when Windows failed to foreground the window.
- **Root Cause**: JARVIS previously relied on simple shell `start` or `open_path` commands without checking `FindWindowW` / `GetForegroundWindow` / `SetForegroundWindow`.
- **Correction**: Built `src/desktop_automation/` containing `WindowManager`, `WindowDetector`, and dedicated application adapters (`WhatsAppAdapter`, `VSCodeAdapter`, `CalculatorAdapter`, `OfficeAdapter`, `ExplorerAdapter`). Single-instance enforcement brings existing windows to front instead of launching duplicates.

### 1.3 Problem C: Volume Control & Reporting Unreliability
- **Observed Defect**: Model claimed "Volume is set to 50%" without knowing what the physical volume was, or failed when attempting PowerShell sound commands.
- **Root Cause**: Lack of Windows Core Audio integration. Python libraries like `pycaw` were not installed.
- **Correction**: Built a pure Python `ctypes` Windows Core Audio controller (`src/system/audio_controller.py`) interacting with `IAudioEndpointVolume` and `IMMDeviceEnumerator` via native COM interfaces. Added scalar normalization `[0.0, 1.0]` <-> `[0, 100]%` and mandatory hardware read-back verification.

### 1.4 Problem D: Missing Real-Time Execution-Stage Visibility
- **Observed Defect**: The user and system only saw "THINKING" or "LISTENING" without knowing whether the agent was classifying, planning, executing, observing, or verifying.
- **Root Cause**: The execution loop had no granular state machine.
- **Correction**: Built `src/agents/task/workflow_state_machine.py` implementing 18 discrete states and emitting structured `ProgressEvent` payloads.

### 1.5 Problem E: Inability to Distinguish New Tasks from Continuations
- **Observed Defect**: When the user said "continue", "next step", or "bhayena feri gara" (it didn't work, do it again), JARVIS treated it as a new question rather than advancing or retrying the active multi-step task.
- **Root Cause**: Lack of intent classification against active task state and lack of multilingual idiom handling.
- **Correction**: Created `src/agents/task/task_classifier.py` with 8 discrete task intents (`NEW_TASK`, `CONTINUE_ACTIVE_TASK`, `MODIFY_ACTIVE_TASK`, `CANCEL_ACTIVE_TASK`, `RESUME_PAUSED_TASK`, `RETRY_FAILED_STEP`, `ANSWER_QUESTION_ABOUT_CURRENT_TASK`, `NEW_TASK_REQUIRING_CONTEXT_SWITCH`).

### 1.6 Problem F: Amnesia Regarding Completed Steps
- **Observed Defect**: JARVIS lost track of which steps had succeeded and which had failed, leading to repeated or omitted actions.
- **Root Cause**: `TaskState` steps were not linked to verified `ExecutionRecord` instances in SQLite and memory prompts.
- **Correction**: Linked `TaskStateManager` and `ExecutionVerifier` to continuously format the step ledger (`[✓] Step 1`, `[▶] Step 2`, `[ ] Step 3`) into the turn prompt.

### 1.7 Problem G: Unverified Success Claims (Anti-Hallucination Failure)
- **Observed Defect**: Model claimed files were created or modified before the OS confirmed the write.
- **Root Cause**: Direct tool returns were treated as ground truth without post-action verification.
- **Correction**: Enforced the 6-Tier Truthfulness Contract in `ExecutionVerifier` (`MODEL proposes -> TOOL executes -> OS reports reality -> VERIFIER confirms reality -> STATE records reality -> MODEL explains reality`).
