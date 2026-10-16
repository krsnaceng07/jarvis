# Supported Desktop Automation Capabilities

1. **Window & Process Management**:
   - Native enumeration on `WinSta0\Default`.
   - Window restoration from minimized state (`ShowWindow(SW_RESTORE)`).
   - Window foreground focus (`SetForegroundWindow`).
   - Responsiveness checking (`IsHungAppWindow`).
2. **WhatsApp Desktop**:
   - Search contacts / groups.
   - Disambiguate duplicate names.
   - Open chat and assert recipient title.
   - Type exact message text.
   - Verify sent message in chat thread.
   - Navigate settings and chat options.
3. **VS Code & Antigravity IDE**:
   - Workspace detection, file opening, terminal command execution, test running, diff inspection.
4. **Claude Code**:
   - Session continuity, command dispatch, test validation.
5. **Office (Word, PowerPoint, Excel)**:
   - Create document/slide, add content, save/export, detect unsaved changes.
6. **Windows Calculator & Settings**:
   - Compute and read display; navigate `ms-settings:` with safety gating.
7. **File Explorer**:
   - Path navigation, item selection, folder creation.
8. **Generic Desktop Fallback**:
   - Window control, keyboard/mouse input, coordinate action fallback with screenshot verification.
