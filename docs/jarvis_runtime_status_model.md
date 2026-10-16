# JARVIS Runtime Status Model & Progress Reporting

**Implementation Reference:** `src/agents/task/workflow_state_machine.py`, `apps/desktop/src/jarvis_desktop/ui.py`  
**OpenClaw Reference:** `src/agents/tools/session-status-tool.ts`, `src/tasks/task-status.ts`

---

## 1. Real-Time Status Representation

JARVIS maintains continuous, structured runtime status to keep both the user and system observers informed of execution progress.

Instead of vague spinning indicators, status is decomposed into three synchronized layers:
1. **Visual Desktop HUD**: Status badge (`LISTENING`, `THINKING`, `SPEAKING`, `MUTED`) with stage subtext.
2. **Workflow Lifecycle State**: The active state in `WorkflowStateMachine` (`PLANNING`, `EXECUTING`, `VERIFYING`, etc.).
3. **Task Step Status**: Step progress in `TaskState` (`Step 2 of 4`).

---

## 2. Status Snapshot Schema

Parity with OpenClaw's `session-status-tool.ts`:

```json
{
  "task_id": "80648c92-88ad-46b2-a4f6-8c4613c7db81",
  "goal": "Backup workspace configuration and clear caches",
  "state": "EXECUTING",
  "current_step_index": 2,
  "total_steps": 3,
  "steps": [
    {
      "step_index": 1,
      "description": "Create backup directory",
      "status": "completed",
      "tool_name": "mkdir",
      "verified": true
    },
    {
      "step_index": 2,
      "description": "Copy configuration files",
      "status": "running",
      "tool_name": "exec",
      "verified": false
    },
    {
      "step_index": 3,
      "description": "Remove temporary caches",
      "status": "pending",
      "tool_name": null,
      "verified": false
    }
  ],
  "seconds_in_state": 1.42,
  "hardware_summary": {
    "cpu_percent": 14.5,
    "memory_percent": 58.2,
    "volume_percent": 42
  }
}
```

---

## 3. Real-Time Progress Event Broadcasting

Whenever `transition()` is called on `WorkflowStateMachine`, all registered listeners receive a `ProgressEvent`. This allows:
- Desktop HUD to display specific stage updates (e.g. `Verifying file creation...`).
- Transcript store to log execution milestones to SQLite.
- Background subagents to coordinate dependencies without polling.
