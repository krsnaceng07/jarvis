# JARVIS UI Explicit State Machine Specification

**Document Compliance:** PRD Section FR-006 & Addendum Section 11

## State Graph

```mermaid
stateDiagram-v2
    [*] --> idle
    idle --> listening : Mic Activated / Speech Onset
    listening --> transcribing : Speech Stream Finalized
    transcribing --> thinking : LLM Prompt Ingestion
    thinking --> speaking : TTS Audio Bytes Ready
    speaking --> listening : Audio Playback Completed
    speaking --> listening : Barge-in Detected (<40ms)
    
    thinking --> tool_running : Autonomous Tool Execution
    tool_running --> thinking : Tool Results Returned
    tool_running --> waiting_for_permission : Destructive Action Guard
    waiting_for_permission --> tool_running : Operator Approved
    
    listening --> cancelling : TERMINATE Clicked
    thinking --> cancelling : TERMINATE Clicked
    tool_running --> cancelling : TERMINATE Clicked
    speaking --> cancelling : TERMINATE Clicked
    
    cancelling --> cancelled : All Tasks Aborted
    cancelled --> idle : Timeout (2.8s) / Reset
    
    idle --> disconnected : Network Drop
    disconnected --> idle : Reconnection Verified
```

## State Invariants
1. **True State Reporting:** "Jarvis is listening" only appears when the microphone capture loop is actually active.
2. **Deterministic Cancellation:** Clicking `TERMINATE` triggers `audioService.playTerminateAlarm()`, drains active queues, stops running tools, and informs the operator without closing the app.
