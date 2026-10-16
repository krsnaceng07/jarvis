# JARVIS Delimited Context Architecture

**Implementation Reference:** `apps/desktop/src/jarvis_desktop/tool_pipeline.py::build_turn_prompt_context`  
**OpenClaw Reference:** `src/agents/internal-runtime-context.ts`, `src/agents/date-time.ts`

---

## 1. Context Assembly Strategy

To prevent hallucinations, temporal disorientation, and task amnesia, JARVIS constructs **standardized delimited context blocks** before every model invocation.

Rather than relying on the LLM's pre-training memory or assumptions, the runtime gathers ground-truth telemetry from the operating system, task ledger, and active window detectors, formatting them into clearly delimited Markdown sections.

---

## 2. Delimited Block Structure

```text
[TEMPORAL CONTEXT]
Current Host Time: 6:45:12 PM (24h: 18:45:12)
Current Host Date: 2026-09-12 (Saturday)
Local Timezone: Asia/Kathmandu (UTC+05:45)
Temporal Grounding Rule: Always use this live clock context for time/date queries.

[TASK INTENT: CONTINUE_ACTIVE_TASK]
Utterance matches continuation keyword with active task.
(Suggested: advance_and_execute_step)

[CONTINUOUS TASK CONTEXT]
Active Goal: Clean temporary files and organize downloads
Task Status: RUNNING
Current Step: Step 2 of 3
  [✓] Step 1: Scan Downloads folder (completed)
  [▶] Step 2: Delete .tmp files (running)
  [ ] Step 3: Archive remaining files (pending)
Most Recent Action: [remove_path] status=success [Verified] at 18:44:30
Continuity Directive: Ground replies in active task. When user says continue, execute next step.

[ACTIVE DESKTOP CONTEXT]
Active Application: Visual Studio Code
Focused Window: jarvis — Visual Studio Code
Window Position: (x=0, y=0, w=1920, h=1040)
Recent Desktop Target: E:\jarvis\src\system\live_clock.py

[RELEVANT MEMORY]
- User prefers English for code comments and Nepali/English for conversation.

[USER UTTERANCE]
continue
```

---

## 3. Delimited Blocks Overview

| Block Delimiter | Generation Source | Purpose |
| :--- | :--- | :--- |
| `## Temporal Context` | `src/system/live_clock.py` | Guarantees microsecond-accurate time, date, and local timezone. |
| `[TASK INTENT]` | `src/agents/task/task_classifier.py` | Explicitly disambiguates new tasks from continuations and retries. |
| `[CONTINUOUS TASK CONTEXT]` | `src/agents/task/task_state.py` | Shows completed steps (`[✓]`), current step (`[▶]`), and verified action logs. |
| `[ACTIVE DESKTOP CONTEXT]` | `src/desktop_automation/` | Reports foreground window, process name, and coordinates. |
| `[RELEVANT MEMORY]` | `extensions/memory_core/` | Injects recalled user preferences and identity facts. |

---

## 4. Anti-Hallucination Invariants

1. **No Temporal Assumption**: The LLM is strictly instructed that any question regarding current date, day of week, or time must be answered using `[TEMPORAL CONTEXT]` or the `system_info` tool.
2. **No Fictitious Action States**: `[CONTINUOUS TASK CONTEXT]` displays only steps marked with physical `ExecutionRecord` verifications.
3. **Deterministic Memory Ingestion**: Contextual injection is filtered and prioritized, keeping the token budget lean and responsive.
