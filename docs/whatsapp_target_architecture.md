# WhatsApp Target Architecture in JARVIS (OpenClaw-Parity Blueprint)

---

## 1. System Execution Pipeline

The complete flow from user intent to verified execution strictly follows the OpenClaw architecture:

```text
User Request ("Send hello to Krishna on WhatsApp")
    ↓
[Input Normalizer & Intent Classifier]
    ↓ (Intent: messaging.whatsapp.send, target: "Krishna", text: "hello")
[Context Resolver & Session Tracker] (Checks active app, recent chat, ongoing tasks)
    ↓
[Capability Discovery & Skill Selection] (Resolves 'whatsapp' skill & required capabilities)
    ↓
[Plugin & Provider Resolution] (Resolves 'extensions/whatsapp' → WhatsAppDesktopProvider)
    ↓
[Structured Tool Registry] (Selects 'whatsapp_send_message' with typed parameters)
    ↓
[Permission & Risk Policy Gate] (Validates risk level, checks recipient confirmation)
    ↓
[Application Session Manager]
    ├── Query PID & HWND
    ├── Check if Iconic (minimized) → Call ShowWindow(SW_RESTORE)
    ├── Apply Win32 foreground lock bypass (AttachThreadInput + Alt key)
    └── Verify user32.GetForegroundWindow() matches WhatsApp HWND
    ↓ (If NOT foreground: ABORT WITH ERROR. Do NOT type.)
[Action Execution & Observation Loop]
    ├── Search contact ("Krishna")
    ├── Assert candidate selection & open chat
    ├── Verify chat header title matches "Krishna"
    ├── Exact text paste via Unicode clipboard
    └── Send key event (Enter)
    ↓
[Post-Action Verification]
    ├── Verify text cleared from message composer
    ├── Confirm message bubble delivered
    └── Update Application Session & Memory Context
    ↓
[Task State & Memory Update] (Marks stage 'completed_verified', updates active recipient)
    ↓
[Truthful Voice/Chat Confirmation] ("Message sent to Krishna on WhatsApp")
```

---

## 2. Core Architectural Components

### 2.1 Provider Abstraction Layer (`src/desktop_automation/providers/`)
A unified, generic `MessagingProvider` protocol implemented by `WhatsAppDesktopProvider` and extensible to future providers (`TelegramDesktopProvider`, `DiscordProvider`, `SlackProvider`):

```python
class MessagingProvider(Protocol):
    app_id: str
    app_name: str

    async def get_state(self) -> ApplicationState: ...
    async def ensure_active(self) -> bool: ...
    async def search_contact(self, query: str) -> list[ContactCandidate]: ...
    async def open_chat(self, recipient: str) -> ActionResult: ...
    async def send_message(self, recipient: str, text: str) -> ActionResult: ...
    async def verify_delivery(self, recipient: str, text: str) -> bool: ...
```

### 2.2 Extension Lifecycle (`extensions/whatsapp/`)
- `jarvis.plugin.json`:
  - Registers plugin `id: "whatsapp"`.
  - Declares tool contracts: `["whatsapp_send_message", "whatsapp_open_chat", "whatsapp_search_contact", "whatsapp_get_state"]`.
  - Binds declarative skill: `"skills": ["./skills"]`.
- `plugin.py`:
  - Registers the provider and tools with `JarvisPluginApi`.
  - Exposes health checks, doctor configuration repairs, and channel event hooks.

### 2.3 Declarative Skill (`extensions/whatsapp/skills/whatsapp/SKILL.md`)
- Provides prompt-level instruction to the LLM with YAML frontmatter.
- Defines rules:
  - Always verify recipient name before sending.
  - Never guess contact when multiple matches exist.
  - Preserve exact dictated text without rewriting or unprompted translations.
  - Do not loop or retry tool calls if a call succeeded.

### 2.4 Granular Structured Tool Registry
Instead of a single ambiguous tool with untyped string arguments, tools are registered individually:
1. `whatsapp_get_state`: Returns whether WhatsApp is running, minimized, or active, and current chat.
2. `whatsapp_open`: Restores, focuses, and unminimizes WhatsApp desktop window.
3. `whatsapp_search_contact`: Searches contacts and returns matching candidate names.
4. `whatsapp_open_chat`: Navigates to a confirmed contact's chat and asserts active header.
5. `whatsapp_send_message`: Pastes and sends the exact message text after verifying foreground.
6. `whatsapp_verify_message`: Checks delivery and post-send state.

### 2.5 Recipient Safety & Risk Control
- **Candidate Evaluation**: When searching contacts, if 2 or more candidates match (e.g. "Krishna Kushwaha" vs "Krishna Sharma"), execution halts and asks the user for clarification.
- **Active Header Match**: Before typing or pasting, the window title or chat header is inspected to ensure it matches the target recipient.
- **Zero Blind Typing**: Under NO circumstance will keystrokes be emitted if `user32.GetForegroundWindow()` does not match the target WhatsApp window.

### 2.6 Task Continuity & Memory Integration
- Tracks active workflow stages in `ActiveDesktopContext`:
  `Stage 1: App Resolved` $\to$ `Stage 2: Restored/Focused` $\to$ `Stage 3: Contact Searched` $\to$ `Stage 4: Chat Confirmed` $\to$ `Stage 5: Text Pasted` $\to$ `Stage 6: Sent` $\to$ `Stage 7: Verified`.
- Subsequent user requests (e.g. "now say thank you") immediately recognize the active conversation stage without repeating search and focus steps unnecessarily.
