# JARVIS Extension & Bundle API Reference

This guide covers declarative extensions, content bundles, and MCP integrations.

---

## 1. Content Bundles

A content bundle is a non-code package under `extensions/<bundle-id>/` containing:
- `openclaw.plugin.json` or bundle manifest.
- Declarative skills under `skills/`.
- MCP server configurations in `mcp.json`.

```json
{
  "id": "dev-bundle",
  "name": "Developer Tools Bundle",
  "kind": "bundle",
  "skills": ["git-workflow", "code-review"],
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "."]
    }
  }
}
```

---

## 2. Declarative Skills

Skills are placed in `skills/<skill_name>/SKILL.md`:

```markdown
---
name: code-review
description: Comprehensive code review workflow
triggers:
  - "review this code"
  - "check my pr"
---

# Code Review Instructions
When requested to review code:
1. Check for security vulnerabilities.
2. Check for type safety and performance regressions.
3. Suggest clean idiomatic refactorings.
```
