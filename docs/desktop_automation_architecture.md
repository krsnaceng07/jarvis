# JARVIS Desktop Automation Architecture

```
User Voice / Text Request
         │
         ▼
DecisionEngine (Intent Analysis & Task Continuity)
         │
         ▼
DesktopRuntime (WinSta0 Session Coordinator)
  ├── ProcessDetector (psutil / toolhelp32)
  ├── WindowDetector (Win32 EnumWindows on WinSta0)
  └── WindowManager (Restore, Focus, Responsiveness)
         │
         ▼
Application Router & Adapters
  ├── WhatsAppDesktopAdapter (Recipient Safety & Exact Text)
  ├── VSCodeAdapter (Workspace, Files, Terminal)
  ├── AntigravityAdapter (Workspace, Agent State, Proof)
  ├── ClaudeCodeAdapter (CLI Session, Diffs, Proof)
  ├── OfficeAdapters (Word, PowerPoint, Excel)
  ├── CalculatorAdapter (Expression, Result Reading)
  ├── SettingsAdapter (ms-settings Navigation, Safety Guard)
  ├── FileExplorerAdapter (Navigation, Selection)
  └── GenericDesktopAdapter (Fallback Window & Control Automation)
         │
         ▼
Observation & Verification Loop (Pre/Post Mutation Proof)
  ├── ActionVerifier (confirmed > unverifiable > suspected_noop)
  └── ScreenshotController (Deduplicated capture)
         │
         ▼
ClaimGroundingFilter (Anti-Hallucination & Truthfulness Gate)
         │
         ▼
Truthful Assistant Response to User
```
