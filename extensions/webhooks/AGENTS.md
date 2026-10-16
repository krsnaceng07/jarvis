# Webhooks Infra Extension (JARVIS)

Full implementation matching OpenClaw `@openclaw/webhooks`.

## Architecture & Capabilities

- **Authenticated Inbound Webhook Routing:**
  - Route registration under `/plugins/webhooks/<routeId>` or custom configured paths.
  - Constant-time secret authentication (`hmac.compare_digest`) via `Authorization: Bearer <secret>`, `X-Jarvis-Secret`, `X-OpenClaw-Secret`, or query parameters.
  - Support for raw secrets and `SecretRefs` (`env`, `file`, `exec`, `store`).
  - In-flight request concurrency limiter and fixed-window rate limiting.
- **TaskFlow Action Dispatching:**
  - `create_flow`, `get_flow`, `list_flows`, `find_latest_flow`, `resolve_flow`, `get_task_summary`
  - `set_waiting`, `resume_flow`, `finish_flow`, `fail_flow`, `request_cancel`, `cancel_flow`
  - `run_task` (supporting `subagent` and `acp` runtimes, status transitions, progress tracking)
- **Diagnostics & Lifecycle:**
  - Doctor contract for route definitions, session key bindings, and path uniqueness.

## Parity status (vs `openclaw-main/extensions/webhooks/`)

| OpenClaw | JARVIS | Status |
|---|---|---|
| `index.ts` / manifest | `plugin.py`, manifests | Complete |
| `config.ts` | `src/config.py` | Complete |
| `http-request-schema.ts` | `src/http_request_schema.py` | Complete |
| `http.ts` | `src/http.py` | Complete |
| Doctor Contract | `src/doctor.py` | Complete |
