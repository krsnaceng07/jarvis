# 1Password Infra Extension (JARVIS)

Full implementation matching OpenClaw `@openclaw/onepassword`.

## Architecture & Surfaces

- **Managed Exec SecretRef Provider:** Resolves `op://<vault>/<item>/<field>` and `op://<vault>/<item>/<section>/<field>` during startup, reload, audit, and apply preflight.
  - Concurrency limited via `asyncio.Semaphore(4)`.
  - Disables 1Password cache (`--cache=false`).
  - Isolated environment with `OP_LOAD_DESKTOP_APP_SETTINGS=false` and `OP_BIOMETRIC_UNLOCK_ENABLED=false`.
- **Policy-Controlled Agent Tool (`onepassword`):**
  - Actions: `list` (returns curated slugs, description, policy, standing grant status; never calls `op` or leaks secrets) and `get` (requires `reason` <= 300 chars, validates single-use authorization nonce).
  - Policy tiers: `auto`, `approve`, `deny`.
  - Standing grants: persisted in SQLite `onepassword_grants` table with `grantTtlHours` (default 720h) and bounded LRU eviction (max 1,024 grants).
  - Bounded in-memory cache with `cacheTtlSeconds` (default 300s); policy evaluated before every cache hit.
  - SQLite audit log in `onepassword_audit_log` (records attempts, never secret values or service tokens).
  - Transcript redaction: post-execution persistence hook replaces values with `[REDACTED: 1Password secret for slug '...']`.
- **CLI Commands:**
  - `jarvis onepassword status` / `openclaw onepassword status`
  - `jarvis onepassword audit [--limit <n>]` / `openclaw onepassword audit [--limit <n>]`
  - `jarvis onepassword secretref status [--json]`
  - `jarvis onepassword secretref setup`

## Parity status (vs `openclaw-main/extensions/onepassword/`)

| OpenClaw | JARVIS | Status |
|---|---|---|
| `index.ts` / manifest | `plugin.py`, manifests | Complete |
| SecretRef Provider | `src/secretref.py`, `src/op_cli.py` | Complete |
| Tool `onepassword` | `src/tool.py` | Complete |
| Storage & Grants | `src/storage.py` | Complete |
| Policy & Caching | `src/policy.py` | Complete |
| CLI & Doctor | `src/cli.py`, `src/doctor.py` | Complete |
