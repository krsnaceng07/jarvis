# OpenClaw Tool Architecture

This document details the tool registration, execution, and security isolation architecture of OpenClaw (`v2026.9.2`).

---

## 1. Tool Factory & Declaration

In OpenClaw, tools are registered dynamically by plugins via factories:

```typescript
api.registerTool((ctx: OpenClawPluginToolContext) => {
  return {
    name: "calculator",
    label: "Calculator",
    description: "Evaluates mathematical expressions safely.",
    parameters: {
      type: "object",
      properties: {
        expression: { type: "string" }
      },
      required: ["expression"]
    },
    execute: async (toolCallId, params, signal, onUpdate) => {
      // Execute within execution context
      return { result: eval(params.expression) };
    }
  };
}, { names: ["calculator"] });
```

---

## 2. Context-Aware Tool Execution (`OpenClawPluginToolContext`)

Tools receive a rich execution context per turn, rather than operating on static globals:
- `agentId`: The active agent handling the conversation.
- `sessionKey`: Canonical session identifier.
- `channelId`: The originating communication channel (e.g. `telegram`, `discord`).
- `senderId`: Platform user ID of the caller.
- `senderIsOwner`: Boolean indicating operator privilege.
- `sandboxed`: Boolean indicating whether execution is constrained to a workspace container.
- `runtimeConfig`: Read-only snapshot of current system configuration.

---

## 3. Security, Approvals & Safe Binaries

Tools executing host processes or file operations pass through multiple policy layers:

1. **Execution Approvals (`src/infra/exec-approvals.ts`)**:
   - Classifies commands into `safe`, `ask`, or `deny`.
   - Sends interactive approval requests via channel buttons or desktop prompt when commands exceed automated thresholds.
2. **Safe Binaries Profile (`src/infra/exec-safe-bin-policy.ts`)**:
   - Maintains an allowlist of permitted CLI executables (`git`, `grep`, `python`, `ls`, etc.).
   - Rejects unlisted or dangerous binaries before spawning processes.
3. **Tool Result Middleware (`src/plugins/agent-tool-result-middleware.ts`)**:
   - Sanitizes and truncates excessive tool outputs to prevent token exhaustion.
   - Applies self-healing repairs for malformed tool returns.
