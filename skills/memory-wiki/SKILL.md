---
name: memory-wiki
description: "Compile, search, inspect, and maintain persistent knowledge wiki pages, structured claims, evidence, and dashboards."
metadata:
  {
    "openclaw":
      {
        "emoji": "📚",
        "requires": { "plugins": ["memory_wiki"] },
      },
  }
---

# Memory Wiki

The `memory_wiki` plugin sits beside the active memory plugin to maintain a curated, navigable knowledge wiki containing entities, concepts, syntheses, claims with structured evidence, and dashboards.

## When to Use

- "Search the wiki for maintainer routing guidelines" (`wiki_search`)
- "Who should I ask for rollout questions?" (`wiki_search mode="route-question"`)
- "Find the Alex person card" (`wiki_search mode="find-person"`)
- "Inspect the claims and evidence for project X" (`wiki_get` / `wiki_search mode="raw-claim"`)
- "Create or update a synthesis page without page surgery" (`wiki_apply`)
- "Check wiki health, contradictions, and open questions" (`wiki_lint` / `wiki_status`)

## Agent Tools

### 1. `wiki_status`
Inspect vault mode (`isolated`, `bridge`, `unsafe-local`), vault scope (`global`, `agent`), resolved agent, health, and Obsidian integration status.

### 2. `wiki_search`
Search across compiled wiki pages and structured claims.
- `query` (string, required): Search query.
- `mode` (string, optional): One of `auto`, `find-person`, `route-question`, `source-evidence`, `raw-claim`.
- `limit` (integer, optional, default: 5): Maximum results.

### 3. `wiki_get`
Retrieve a specific wiki page by ID or path (`entity.foo`, `concept.bar`, `syntheses/baz.md`).
- `id` or `path` (string, required): Page identifier or relative path.

### 4. `wiki_apply`
Apply a structured synthesis or metadata mutation without freeform Markdown surgery.
- `kind`: `synthesis` or `metadata`.
- `title`, `body`, `sourceId`, `metadata`.

### 5. `wiki_lint`
Run structural checks, open question analysis, and contradiction detection across the wiki.

## CLI Commands

```bash
openclaw wiki status
openclaw wiki doctor
openclaw wiki init
openclaw wiki compile
openclaw wiki lint
openclaw wiki search "alpha"
openclaw wiki get entity.alpha
openclaw wiki apply synthesis "Alpha Summary" --body "..." --source-id source.alpha
openclaw wiki okf import ./bundles/my-catalog
openclaw wiki bridge import
openclaw wiki obsidian status
```
