# WhatsApp Tool Contracts Specification

**Module:** `src/desktop_automation/tools/whatsapp_tools.py`  
**OpenClaw Parity:** Granular, schema-validated, strongly-typed tool definitions.  

---

## 1. `whatsapp_get_state`
- **Purpose**: Non-intrusive inspection of WhatsApp runtime state.
- **Parameters**: None.
- **Risk Level**: None / Read-only.
- **Idempotency**: Fully idempotent.
- **Returns**: String summary containing `Running` (bool), `Minimized` (bool), `Foreground` (bool), `Active Chat` (str), and `Window Title` (str).
- **Failure Modes**: Application not running $\to$ returns `Running=False`.

---

## 2. `whatsapp_open`
- **Purpose**: Brings WhatsApp Desktop to the active foreground. If minimized, unminimizes via `ShowWindow(SW_RESTORE)` and unlocks the Windows OS foreground lock via `AttachThreadInput` and synthetic Alt event.
- **Parameters**: None.
- **Risk Level**: Low.
- **Idempotency**: Idempotent.
- **Verification**: Queries `user32.GetForegroundWindow()` to assert that the active foreground HWND or PID matches WhatsApp.
- **Failure Modes**: Application not installed or unresponsive.

---

## 3. `whatsapp_search_contact`
- **Purpose**: Searches contacts or conversations using the search bar.
- **Parameters**:
  - `query` (string, required): Contact name, partial name, or phone number.
- **Risk Level**: Low.
- **Idempotency**: Idempotent.
- **Preconditions**: Target window must be in active foreground. If not, auto-restores first.
- **Returns**: Formatted list of candidate names. If ambiguous, prompts for user disambiguation.

---

## 4. `whatsapp_open_chat`
- **Purpose**: Selects a contact, opens the conversation thread, and asserts that the chat header reflects the intended recipient.
- **Parameters**:
  - `recipient` (string, required): Exact or resolved recipient name.
- **Risk Level**: Low.
- **Idempotency**: Idempotent.
- **Verification**: Asserts window title and active recipient context match `recipient`.

---

## 5. `whatsapp_send_message`
- **Purpose**: Pastes exact text into the message composer and triggers the send event (Enter).
- **Parameters**:
  - `recipient` (string, required): Destination contact name.
  - `message` (string, required): Exact message text.
- **Risk Level**: High (external communication).
- **Idempotency**: Idempotency-protected. Duplicated calls within 5 seconds with identical text are blocked.
- **Verification**:
  1. Win32 foreground check before keystrokes (zero blind typing).
  2. Unicode clipboard paste preserving emojis, newlines, and exact punctuation.
  3. Delivery check verifying active conversation.
- **Failure Modes**:
  - `WhatsApp is not in the active foreground` $\to$ ABORT.
  - `Recipient name is required` $\to$ ABORT.
  - `Message text cannot be empty` $\to$ ABORT.

---

## 6. `whatsapp_verify_message`
- **Purpose**: Post-send observation asserting that the message has left the composer and is recorded in the active chat history.
- **Parameters**:
  - `recipient` (string, required): Target recipient.
  - `message` (string, optional): Sent text snippet.
- **Risk Level**: Read-only.
- **Returns**: Verification outcome boolean and detail string.
