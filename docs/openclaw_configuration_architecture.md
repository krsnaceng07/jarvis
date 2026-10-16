# OpenClaw Configuration Architecture

This document details the configuration system, schema enforcement, and migration model of OpenClaw (`v2026.9.2`).

---

## 1. Single Canonical Config File

OpenClaw reads and writes a single canonical configuration file:
- **Path**: `~/.openclaw/config.json` (or `~/.jarvis/config.json`).
- **Validation**: Enforced by JSON Schema (`config-contracts`).
- **Strict Shape**: Steady-state runtime accepts only the latest schema shape; no legacy shims or fallback readers exist in hot runtime paths.

---

## 2. Automated Migrations (`openclaw doctor --fix`)

When schema versions advance or options are renamed:
1. The steady-state runtime does not maintain runtime aliases or silent compatibility shims.
2. Older configurations are migrated explicitly via `openclaw doctor --fix`.
3. Plugins declare doctor contracts (`doctorContract: { configRepair: true }`).
4. Repaired configurations are atomically written to disk with backups.

---

## 3. Multi-Channel & Multi-Account Shape

```json
{
  "channels": {
    "telegram": {
      "enabled": true,
      "botToken": "secret://telegram-token",
      "accounts": {
        "bot_support": {
          "enabled": true,
          "botToken": "secret://telegram-support-token"
        }
      }
    },
    "whatsapp": {
      "enabled": true
    }
  },
  "models": {
    "default": "gemini-flash",
    "providers": {
      "google": { "apiKey": "env:GEMINI_API_KEY" }
    }
  }
}
```

Secrets are resolved securely via indirect references (`env:VAR_NAME`, `secret://vault_key`, or local file paths).
