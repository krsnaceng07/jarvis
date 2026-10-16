# Task Continuity & Pronoun Resolution Model

JARVIS treats user commands across multi-turn sessions as continuations of active workflows.

## Resolution Rules
1. **Pronoun Resolution**:
   - *"his chat"* / *"her chat"* $ightarrow$ resolves to the contact currently selected or searched in `ActiveDesktopContext`.
   - *"it"* $ightarrow$ resolves to the active document, message, or file.
   - *"send it"* $ightarrow$ triggers sending the verified pending message without re-typing.
   - *"save it"* $ightarrow$ executes document save on the active editor.
2. **Context Preservation**:
   - If WhatsApp is already open with John's chat active, a command *"Tell him I'm late"* immediately reuses the active chat without searching again.
