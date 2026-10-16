# OpenClaw vs JARVIS Desktop Automation Parity Matrix

| Dimension | OpenClaw Requirement | JARVIS Target Architecture | Parity Status |
| :--- | :--- | :--- | :---: |
| **1. Execution Serialization** | Sequential operation queue (`serialize`) to prevent race conditions | `DesktopRuntime` operation lock chaining execution | **PARITY** |
| **2. Window Discovery** | `list_apps`, `list_windows`, PID/Window ID resolution | `ProcessDetector` + `WindowDetector` on `WinSta0\Default` | **PARITY** |
| **3. Window Reuse & Focus** | Focus existing window; do not launch duplicates | `WindowManager.find_window_for_app` + `focus_window` | **PARITY** |
| **4. Active Desktop Context** | Track active window, control, task, workflow stage | `ActiveDesktopContext` injected before LLM turn | **PARITY** |
| **5. Task Continuity** | Multi-turn reference resolution (*"it"*, *"him"*, *"send it"*) | `TaskContinuityResolver` with pronoun resolution | **PARITY** |
| **6. WhatsApp Desktop** | Search, recipient validation, exact text, verify sent | `WhatsAppDesktopAdapter` with wrong-recipient guard | **PARITY** |
| **7. IDE & Agent Adapters** | VS Code, Antigravity, Claude Code context & tasks | Specialized adapters for VS Code, Antigravity, Claude | **PARITY** |
| **8. Office & System Apps** | Word, PowerPoint, Excel, Calc, Settings, Explorer | Dedicated adapters with unsaved change detection | **PARITY** |
| **9. Generic Fallback** | Control any window via accessibility/coordinates | `GenericDesktopAdapter` with UI hierarchy & visual OCR | **PARITY** |
| **10. Observation Loop** | Screenshot after action; unchanged frame deduplication | `ObservationLoop` with perceptual hash comparison | **PARITY** |
| **11. Safety & Confirmation** | Confirmation for external effects (messaging, delete) | `ConfirmationManager` + `RecipientGuard` | **PARITY** |
| **12. Absolute Truthfulness** | Refuse unverified success claims; no hallucination | `ClaimGroundingFilter` + `ActionVerifier` | **PARITY** |
