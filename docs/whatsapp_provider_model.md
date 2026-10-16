# WhatsApp Provider Model & Extensibility Architecture

**Package:** `src/desktop_automation/providers/`  
**OpenClaw Parity:** Unified provider abstraction decoupling intent from concrete platform implementations.  

---

## 1. Architecture Overview

To prevent WhatsApp from being a special hardcoded exception in the brain, JARVIS establishes a **Provider Abstraction Model**:

```text
               ┌────────────────────────┐
               │    JARVIS Brain /      │
               │  Intent Classifier     │
               └───────────┬────────────┘
                           │ Resolves provider by capability
                           ▼
               ┌────────────────────────┐
               │    ProviderRegistry    │
               └───────────┬────────────┘
                           │
       ┌───────────────────┼───────────────────┐
       ▼                   ▼                   ▼
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│   WhatsApp   │    │   Telegram   │    │   Discord    │
│   Provider   │    │   Provider   │    │   Provider   │
└──────┬───────┘    └──────────────┘    └──────────────┘
       │
       ├─────────────────────────┐
       ▼                         ▼
┌──────────────┐          ┌──────────────┐
│   Desktop    │          │     Web      │
│   Adapter    │          │   Adapter    │
└──────────────┘          └──────────────┘
```

---

## 2. Core Protocol (`BaseMessagingProvider`)

Defined in `src/desktop_automation/providers/base_provider.py`:

```python
class BaseMessagingProvider(ABC):
    app_id: str
    app_name: str

    @abstractmethod
    async def get_state(self) -> ApplicationState:
        """Inspect and return running, minimized, and foreground state."""
        ...

    @abstractmethod
    async def ensure_active(self) -> bool:
        """Unminimize, restore, and verify foreground acquisition."""
        ...

    @abstractmethod
    async def search_contacts(self, query: str) -> List[ContactCandidate]:
        """Search contacts and return disambiguated candidate list."""
        ...

    @abstractmethod
    async def open_chat(self, recipient: str) -> ProviderActionResult:
        """Open chat thread and assert header title match."""
        ...

    @abstractmethod
    async def send_message(self, recipient: str, message: str) -> ProviderActionResult:
        """Paste exact text, trigger send, and verify delivery."""
        ...

    @abstractmethod
    async def verify_delivery(self, recipient: str, message: str) -> bool:
        """Observe post-send delivery status in conversation."""
        ...
```

---

## 3. Dynamic Registry (`ProviderRegistry`)

`ProviderRegistry` (in `src/desktop_automation/providers/registry.py`) dynamically maps provider IDs to implementations:
- `registry.register_provider(WhatsAppDesktopProvider())`
- `registry.get_provider("whatsapp")`

### Clean Extensibility for Future Apps
Adding Telegram, Slack, or Discord requires only:
1. Creating `TelegramDesktopProvider(BaseMessagingProvider)`.
2. Calling `registry.register_provider(TelegramDesktopProvider())`.
3. Declaring tools in `extensions/telegram/`.
**Zero modifications to the core orchestrator, brain, or speech loop are required.**
