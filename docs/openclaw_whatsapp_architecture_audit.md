# OpenClaw WhatsApp Architecture Audit

**Repository Path:** `c:/Users/kcs23/Downloads/openclaw-main`  
**Package Version:** `2026.9.2` (schema versions: state `16`, agent `19`)  
**License:** MIT, OpenClaw Foundation  

---

## 1. Overview & Architecture Philosophy in OpenClaw

In OpenClaw, WhatsApp is not a one-off Python script or ad-hoc subshell hack. It is implemented as a **first-class modular extension** located in `extensions/whatsapp/`, adhering strictly to OpenClaw's multi-tier extension contract:

1. **Extension Manifest (`openclaw.plugin.json`)**: Declares plugin identity, contracts, activation rules, channel capabilities, and configuration schema.
2. **Channel Plugin Contract (`api.ts` & `channel-plugin-api.ts`)**: Integrates with OpenClaw's unified channel gateway for bidirectional messaging, pairing, session state, and presence.
3. **Agent Tool Registry (`agent-tools-api.ts` & `src/agent-tools-*.ts`)**: Registers strongly-typed, schema-validated tools (`whatsapp_call`, `whatsapp_login`) callable by the agent runtime.
4. **Declarative Skill (`skills/wacli/SKILL.md`)**: Provides LLM guidance, usage boundaries, CLI prerequisites, safety gates, and workflow protocols.
5. **Provider / Protocol Engine**: Connects via official/legitimate companion services (such as `whatsmeow`, `wacli`, and `meowcaller`) without fragile, unverified hacks.
6. **Execution Context & Action Gating (`createActionGate`)**: Ensures account resolution, rate limits, concurrency locking (`activeCallAccounts`), and safe recipient evaluation before dispatch.

---

## 2. Directory Structure of `extensions/whatsapp/` in OpenClaw

```text
extensions/whatsapp/
├── openclaw.plugin.json            # Extension manifest
├── package.json                    # Workspace dependencies
├── index.ts                        # Main barrel export
├── api.ts                          # Public plugin API entry
├── runtime-api.ts                  # Runtime instantiation & wiring
├── contract-api.ts                 # Channel & doctor contracts
├── agent-tools-api.ts              # Agent tool discovery facade
├── auth-presence.ts                # Account auth & presence tracking
├── login-qr-api.ts                 # QR code login flow
├── skills/
│   └── wacli/
│       └── SKILL.md                # Declarative agent skill with YAML frontmatter
└── src/
    ├── accounts.ts                 # Account normalization and credential retrieval
    ├── agent-tools-call.ts         # 'whatsapp_call' tool implementation
    ├── agent-tools-login.ts        # 'whatsapp_login' tool implementation
    ├── connection-controller.ts    # WhatsApp connection & socket lifecycle
    ├── targets-runtime.ts          # Recipient JID & E.164 normalization
    └── ...
```

---

## 3. Extension Manifest Contract (`openclaw.plugin.json`)

Source proof (`extensions/whatsapp/openclaw.plugin.json:1-33`):
```json
{
  "id": "whatsapp",
  "doctorContract": {
    "configRepair": true,
    "stateMigrations": [{ "id": "whatsapp-legacy-state" }]
  },
  "name": "WhatsApp",
  "description": "OpenClaw WhatsApp channel plugin for WhatsApp Web chats.",
  "skills": ["./skills"],
  "activation": {
    "onStartup": false
  },
  "contracts": {
    "tools": ["whatsapp_call", "whatsapp_login"]
  },
  "channels": ["whatsapp"],
  "configSchema": {
    "type": "object",
    "additionalProperties": false,
    "properties": {
      "pluginHooks": {
        "type": "object",
        "additionalProperties": false,
        "properties": {
          "messageReceived": {
            "type": "boolean",
            "description": "Opt in to broadcasting inbound WhatsApp message_received hook payloads to loaded plugins."
          }
        }
      }
    }
  }
}
```

### Key Manifest Invariants
- **Dynamic Skill Binding**: `"skills": ["./skills"]` automatically discovers subdirectories containing `SKILL.md` (e.g. `wacli`).
- **Explicit Tool Contracts**: `"contracts": { "tools": ["whatsapp_call", "whatsapp_login"] }` declares the tool surface upfront so the agent runtime can discover tools during schema compilation without loading heavy dependencies.
- **Channel Membership**: `"channels": ["whatsapp"]` binds into the channel router (`packages/channels_core`).

---

## 4. Agent Tool Registration & Safety Contracts

Source proof (`extensions/whatsapp/src/agent-tools-call.ts:36-53`):
```typescript
// One whatsmeow session database must not be driven by concurrent companion clients.
// Reject overlap so model retries cannot duplicate calls or contend on auth state.
const activeCallAccounts = new Set<string>();

const WhatsAppCallToolSchema = Type.Object(
  {
    action: stringEnum(["status", "call"] as const, {
      description: "Check MeowCaller setup or call the current WhatsApp requester",
    }),
    message: Type.Optional(
      Type.String({
        description: "Spoken message to play after the requester answers (maximum 60 seconds)",
        maxLength: MAX_MESSAGE_LENGTH,
      }),
    ),
  },
  { additionalProperties: false },
);
```

### Safety & Concurrency Principles in OpenClaw Tools
1. **Concurrency Lock / Idempotency**: `activeCallAccounts.has(accountId)` prevents duplicated calls and race conditions.
2. **Strict Parameter Validation**: Schemas use TypeBox with `additionalProperties: false` and strict `maxLength`.
3. **Recipient Resolution Gate**:
   ```typescript
   const target = await resolveRequesterE164({ accountId, cfg, requesterSenderId });
   if (!target) {
     throw new Error("Could not resolve the current WhatsApp requester to a phone number");
   }
   ```
4. **Self-Call Prevention**: Prevents the agent from messaging or calling its own linked number.
5. **Truthful Outcome Reporting**: Result returns `jsonResult({ completed: true, recipient: ... })` or raises structured errors. Never fabricates success.

---

## 5. Declarative Skill Model (`SKILL.md`)

Source proof (`extensions/whatsapp/skills/wacli/SKILL.md:1-43`):
```markdown
---
name: wacli
description: "Send third-party WhatsApp messages or sync/search WhatsApp history via wacli, not normal active chats."
homepage: https://wacli.sh
metadata:
  {
    "openclaw":
      {
        "emoji": "📱",
        "requires": { "bins": ["wacli"] },
      },
  }
---

# wacli
Use `wacli` only when the user explicitly asks you to message someone else on WhatsApp...
Safety:
- Require explicit recipient + message text.
- Confirm recipient + message before sending.
- If anything is ambiguous, ask a clarifying question.
```

### Principles of Skills in OpenClaw
- Skills guide LLM intent resolution and provide operational guardrails.
- They define prerequisites (e.g. required binaries or permissions).
- They declare what is supported vs. when NOT to invoke the tool.

---

## 6. What OpenClaw Has vs. What JARVIS Needs

| OpenClaw Architecture | OpenClaw Implementation | JARVIS Parity Requirement |
|:---|:---|:---|
| **Extension Type** | Headless server/channel plugin (`whatsmeow` / `wacli`) | Must support both Channel Gateway and Windows Desktop UI / Web Provider |
| **Plugin Packaging** | `extensions/whatsapp/openclaw.plugin.json` | `extensions/whatsapp/jarvis.plugin.json` |
| **Skill Definition** | `extensions/whatsapp/skills/wacli/SKILL.md` | `skills/whatsapp/SKILL.md` and `extensions/whatsapp/skills/whatsapp/SKILL.md` |
| **Tool Registry** | `api.registerTool(...)` via `JarvisPluginApi` | Registered in tool pipeline via `jarvis_sdk.tool_plugin` |
| **Recipient Gate** | E.164 and JID strict resolution | `RecipientGuard` with search disambiguation & active chat header match |
| **Host Automation** | CLI binary execution (`meowcaller`, `wacli`) | Win32 native window & process manager + URI protocol fallback |
| **Observation** | CLI JSON status return | Win32 foreground check + UI verification before & after typing |
| **Truthfulness** | Strictly raises errors on failure; no fake success | Disallows completion unless verified on screen or via delivery check |
