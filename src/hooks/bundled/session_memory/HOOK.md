---
name: session-memory
description: Injects active memory context into agent sessions at session start.
events: ["session:start", "agent:bootstrap"]
always: true
emoji: "🧠"
hookKey: session-memory
---

# Session Memory Hook

Fires on `session:start` and `agent:bootstrap` to inject the operator's
active memory context into the agent's system prompt. Mirrors OpenClaw's
`bundled/session-memory` hook.
