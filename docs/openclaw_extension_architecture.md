# OpenClaw Extension Architecture

This document defines the taxonomy and execution models for extending OpenClaw (`v2026.9.2`).

---

## 1. Extension Taxonomy

OpenClaw defines four distinct extension tiers, each designed for specific isolation and capability requirements:

```text
┌────────────────────────────────────────────────────────┐
│                   EXTENSION TIERS                      │
├────────────────────┬───────────────────────────────────┤
│ Tier 1: Packages   │ packages/* (Core Shared Contracts)│
│ Tier 2: Plugins    │ extensions/* with code & manifest │
│ Tier 3: Bundles    │ extensions/* declarative content  │
│ Tier 4: Skills     │ skills/* markdown workflows       │
└────────────────────┴───────────────────────────────────┘
```

### 1. Workspace Packages (`packages/*`)
- Fixed internal libraries that compile into the host binary or distribution.
- Examples: `plugin-sdk`, `agent-core`, `gateway-protocol`, `channels-core`.
- Used when types or protocols must be shared across plugins without duplicating logic.

### 2. Code-Executing Bundled Plugins (`extensions/*`)
- Shipped with `openclaw.plugin.json` manifest and an executable entrypoint.
- Execute arbitrary platform logic within Node/Python runtime.
- Implement channels (Telegram, WhatsApp), model providers (OpenAI, Anthropic), or hardware integrations.

### 3. Declarative Content Bundles (`extensions/*`)
- Lightweight packages without code entrypoints.
- Shipped with bundle manifest declaring:
  - Bundled Skills (`SKILL.md`)
  - Pre-packaged slash commands
  - Model Context Protocol (MCP) server definitions
- Discovered and activated alongside native code plugins.

### 4. Declarative Skills (`skills/*`)
- Plain markdown files with YAML frontmatter.
- Zero runtime dependencies; parsed directly into agent prompts when semantic triggers match.

---

## 2. Load Order & Dependency Resolution

During bootstrap, the host orders extension activation:

1. **Core Packages** (Static import).
2. **Infrastructure & Secret Plugins** (`vault`, `1password`).
3. **Storage & Memory Plugins** (`memory-core`, `memory-lancedb`).
4. **Model Providers** (`openai`, `anthropic`, `google`).
5. **Tool & Service Plugins** (`browser`, `bash`, `firecrawl`).
6. **Content Bundles & Declarative Skills**.
7. **Messaging Channels** (`telegram`, `whatsapp`, `discord`).

Channels are loaded last to ensure all model providers, tools, and memory systems are fully operational before incoming messages are accepted.
