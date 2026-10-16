# Vault Infra Extension (JARVIS)

Full implementation matching OpenClaw `@openclaw/vault`.

## Architecture & Capabilities

- **Managed HTTP SecretRef Provider:** Resolves `<vault-secret-path>/<field>` from HashiCorp Vault at Gateway startup and reload time.
  - Direct HTTP/REST client talking to Vault server (does not require the `vault` CLI).
  - KV v2 (`/v1/<mount>/data/<path> -> data.data.<field>`) and KV v1 (`/v1/<mount>/<path> -> data.<field>`) engine support.
  - Authentication methods:
    - `token`: Client token via `VAULT_TOKEN`.
    - `token_file`: Token sink file via `VAULT_TOKEN_FILE` / `OPENCLAW_VAULT_TOKEN_FILE`.
    - `jwt`: Workload JWT file login via `OPENCLAW_VAULT_JWT_FILE` and `OPENCLAW_VAULT_AUTH_ROLE`.
    - `kubernetes`: Service-account token login via `/var/run/secrets/kubernetes.io/serviceaccount/token` and `OPENCLAW_VAULT_AUTH_ROLE`.
  - Enterprise namespaces: `VAULT_NAMESPACE` header (`X-Vault-Namespace`).
  - In-memory caching for resolved secret refs during a session.
- **CLI Commands:**
  - `jarvis vault status [--provider-alias <alias>]` / `openclaw vault status`
  - `jarvis vault setup` / `openclaw vault setup` (`--openai-id`, `--anthropic-id`, `--openrouter-id`, `--provider-key`, `--target`)

## Parity status (vs `openclaw-main/extensions/vault/`)

| OpenClaw | JARVIS | Status |
|---|---|---|
| `index.ts` / manifest | `plugin.py`, manifests | Complete |
| Auth & Client | `src/auth.py`, `src/client.py` | Complete |
| SecretRef Provider | `src/secretref.py` | Complete |
| CLI & Doctor | `src/cli.py`, `src/doctor.py` | Complete |
