---
name: memory-lancedb
description: "Store, recall, search, and manage long-term vector memories using LanceDB."
metadata:
  {
    "openclaw":
      {
        "emoji": "🧠",
        "requires": { "plugins": ["memory_lancedb"] },
      },
  }
---

# Memory LanceDB

The `memory_lancedb` plugin provides long-term vector memory stored in LanceDB with auto-recall and auto-capture capabilities.

## When to Use

- "Remember that I prefer TypeScript with strict typing."
- "Recall my preferences about code formatting."
- "Search long-term memory for my deployment notes."
- "Forget the memory with ID 1234-5678-..."

## Tools

### 1. `memory_recall`
Vector search over stored long-term memories for the current agent.

- `query` (string, required): Search query or phrase to match against memories.
- `limit` (integer, optional, default: 5): Maximum number of memories to return.

### 2. `memory_store`
Save important facts, preferences, decisions, or entities in long-term vector memory.

- `text` (string, required): Information to remember.
- `importance` (number, optional, default: 0.7): Importance score from 0.0 to 1.0.
- `category` (string, optional): One of `preference`, `fact`, `decision`, `entity`, or `other`.

### 3. `memory_forget`
Delete specific memories by ID or search query (GDPR-compliant).

- `memoryId` (string, optional): Specific memory UUID to delete.
- `query` (string, optional): Search query to find candidate memories to forget.

## CLI Commands

```bash
openclaw ltm list [--agent <id>] [--limit <n>] [--order-by-created-at]
openclaw ltm search <query> [--agent <id>] [--limit <n>]
openclaw ltm stats [--agent <id>]
openclaw ltm query [--agent <id>] [--cols <columns>] [--filter <condition>] [--limit <n>] [--order-by <column>:<asc|desc>]
```
