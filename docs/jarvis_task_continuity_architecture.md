# JARVIS Task Continuity & Multi-Step Ledger Architecture

**Implementation Reference:** `src/agents/task/task_state.py`, `src/agents/task/task_classifier.py`  
**OpenClaw Reference:** `src/tasks/task-status.ts`

---

## 1. The Multi-Turn Amnesia Problem

In traditional voice and chat assistants, each conversation turn is treated as an isolated question-and-answer cycle. When a user requests a multi-step procedure (such as "clean temporary files, organize downloads, and create a backup"), the assistant often:
1. Executes step 1.
2. Forgets the original goal on turn 2.
3. Asks "How can I help you today?" when the user says "continue".
4. Starts over from scratch when the user says "it didn't work, try again".

---

## 2. The Task Ledger & State Machine

JARVIS introduces a continuous **Task Ledger** maintained by `TaskStateManager`.

A task consists of:
- **`task_id`**: Unique identifier persisted in SQLite.
- **`goal`**: The high-level objective stated by the user.
- **`steps`**: An ordered list of `TaskStep` objects, each tracking its `step_index`, `description`, `status` (`pending`, `running`, `completed`, `failed`), and linked `ExecutionRecord`.
- **`current_step_index`**: The active pointer indicating which step is currently executing or next in line.
- **`modified_files`**: List of files created or edited during the task.

```text
[CONTINUOUS TASK CONTEXT]
Active Goal: Clean temporary files and organize downloads
Task Status: RUNNING
Current Step: Step 2 of 3
  [✓] Step 1: Scan Downloads folder for temp files (completed)
  [▶] Step 2: Delete .tmp files (running)
  [ ] Step 3: Move remaining files to Archives (pending)
Modified Files: E:\Downloads\cache.tmp
Most Recent Action: [remove_path] status=success [Verified] at 18:44:30
```

---

## 3. Multilingual Intent Classification (`TaskClassifier`)

Whenever a user speaks or submits text, `TaskClassifier` evaluates the input against the active task ledger, determining whether the turn is:

1. **`NEW_TASK`**: A brand new independent command (e.g. "What's the weather?").
2. **`CONTINUE_ACTIVE_TASK`**: Proceeding to the next step. Matches:
   - English: "continue", "proceed", "next", "go ahead", "keep going".
   - Nepali: "aagadi badha", "pachhi ko gara", "arko gara", "continue gara".
3. **`RETRY_FAILED_STEP`**: Re-attempting a step that failed. Matches:
   - English: "retry", "try again", "do it again".
   - Nepali: "bhayena feri gara", "chaina feri", "feri prayas gara", "feri gar".
4. **`CANCEL_ACTIVE_TASK`**: Aborting the task. Matches:
   - English: "cancel", "stop this", "nevermind".
   - Nepali: "chhodideu", "rokka gara", "banda gara yo".
5. **`RESUME_PAUSED_TASK`**: Unpausing a suspended task ("resume", "rokeko bata suru gara").
6. **`ANSWER_QUESTION_ABOUT_CURRENT_TASK`**: Status query ("what are you doing?", "k gardai chhau?", "progress k chha?").
7. **`NEW_TASK_REQUIRING_CONTEXT_SWITCH`**: Explicitly dropping the current task for a new priority ("instead, do this", "yo chhodera arko gara").

---

## 4. Contextual Pronoun Resolution

The `TaskContinuity` resolver in `src/desktop_automation/core/task_continuity.py` handles conversational pronouns and short instructions:
- "send it" / "pathaideu" -> Uses text from the previous message and focuses the active messaging window (WhatsApp).
- "save it" / "rakha" -> Triggers file save hotkey `Ctrl + S` on the active window.
- "close it" / "banda gara" -> Closes the active window or process.
