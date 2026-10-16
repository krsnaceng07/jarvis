# JARVIS Target Architecture

This document defines the unified target architecture for JARVIS as an OpenClaw-parity agent platform.

---

## 1. System Architecture Diagram

```text
┌────────────────────────────────────────────────────────────────────────┐
│                        USER / CHANNELS / CLIENTS                       │
├───────────────┬────────────────┬─────────────────┬─────────────────────┤
│ Telegram Bot  │ WhatsApp Agent │ PyQt6 Desktop   │ Headless Gateway CLI│
└───────┬───────┴────────┬───────┴────────┬────────┴──────────┬──────────┘
        │                │                │                   │
        ▼                ▼                ▼                   ▼
┌────────────────────────────────────────────────────────────────────────┐
│                CHANNELS & ADAPTER CORE (packages/channels_core)        │
├────────────────────────────────────────────────────────────────────────┤
│ • Inbound Normalization (InboundMessage)                               │
│ • 5-Stage Turn Runner (ingest -> classify -> preflight -> assemble)    │
│ • Session Routing (channel:accountId:peerId[:topic:threadId])          │
│ • Binding Registry (subagent / task continuity)                        │
│ • Outbound Delivery (draft previews, rich blocks, media, typing)       │
└──────────────────────────────────┬─────────────────────────────────────┘
                                   │
                                   ▼
┌────────────────────────────────────────────────────────────────────────┐
│               AGENT CORE & PLUGIN SDK (packages/plugin_sdk)            │
├────────────────────────────────────────────────────────────────────────┤
│ • PluginRegistry (Multi-channel, providers, tools, hooks, lifecycles)  │
│ • Discovery & Loader (extensions/*/openclaw.plugin.json)               │
│ • HookBus (Async event emission with error isolation)                  │
│ • Tool Execution Pipeline (context injection, approval policies)       │
│ • Self-Healing Loop (tool call repair, autonomous remediation)         │
└──────────────────────────────────┬─────────────────────────────────────┘
                                   │
        ┌──────────────────────────┴──────────────────────────┐
        ▼                                                     ▼
┌──────────────────────────────────────┐  ┌──────────────────────────────┐
│  PERSISTENT STORAGE & RETRIEVAL      │  │  INFERENCE & MEDIA PROVIDERS │
├──────────────────────────────────────┤  ├──────────────────────────────┤
│ • SQLite Store (~/.jarvis/state/)    │  │ • Google Gemini (Live API)   │
│ • Memory Core (FTS5 + CJK keywords)  │  │ • Groq LLaMA / DeepSeek      │
│ • LanceDB Embeddings & Vectors       │  │ • ElevenLabs & Fish Audio    │
│ • Task Ledger & Session Compaction   │  │ • Vision & OCR Understanding │
└──────────────────────────────────────┘  └──────────────────────────────┘
```
