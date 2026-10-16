---
name: beam
description: Discover, sanitize, redact, and upload local coding-session snapshots (Claude Code, Codex) to a remote Beam receiver gateway over authenticated HTTP.
---

# Beam Skill

Discover, sanitize, redact, and upload local coding-session transcripts to a remote Beam receiver.

## Workflow

1. **Discover Local Sessions:**
   - Scan local coding session storage for Claude Code (`~/.claude/sessions/` or `~/.claude.json`) and Codex (`~/.codex/sessions/`).
   - Identify the most recent or targeted session to beam.

2. **Sanitize & Redact:**
   - Strip all sensitive credentials, auth tokens, cookies, passwords, and private API keys.
   - Replace raw tool results, reasoning blocks, and local file paths with compact counts (e.g. `3 read, 2 write, 1 execute; raw tool outputs dropped: 4`).
   - Retain only clean, chronological `userMessage`, `agentMessage`, and `other` items.
   - Ensure total items count $\le 200$, item text $\le 6,000$ characters, and total payload size $\le 56\text{ KiB}$.

3. **Authenticate:**
   - For Cloudflare Access: authenticate via `cloudflared access login <gateway-url>`.
   - For Token/Password Auth: use `Authorization: Bearer <gateway-token>`.

4. **Upload Snapshot:**
   - Send `POST /api/v1/beam/sessions` with the JSON payload.
   ```bash
   curl -sS https://<gateway-host>/api/v1/beam/sessions \
     -H 'Authorization: Bearer <token>' \
     -H 'Content-Type: application/json' \
     -d @snapshot.json
   ```

5. **Report Result:**
   - Extract the returned `beamId` and `url` (e.g. `/beam/fix-the-upload-flow-0123456789ab`).
   - Provide the clickable link to the user for Control UI inspection or Team continuation.
