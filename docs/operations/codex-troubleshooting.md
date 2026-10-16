# Codex Harness Troubleshooting

Symptoms, causes, and fixes for the JARVIS Codex app-server harness. The
runtime follows OpenClaw's ownership model: JARVIS selects and authorizes the
harness, while the Codex app-server owns native threads, turns, shell, MCP,
and native tool execution.

## First checks

Run the read-only checks before changing configuration:

```text
/codex status
uv run jarvis doctor codex/managed-app-server
uv run jarvis status
```

Use `/codex computer-use status` for Computer Use readiness. Do not paste
API keys, OAuth tokens, authorization headers, or full environment dumps into
logs or bug reports.

## Troubleshooting

### Codex is not available as a normal model provider

This is expected for the app-server harness. Select an `openai/gpt-*` model,
ensure the Codex extension is enabled, and check that an extension allowlist
does not exclude `codex`.

In JARVIS, the provider descriptor is exposed by
`extensions/codex/plugin.py`, while native harness selection is decided by
`CodexAgentHarness.supports()`. A plain model prefix is not proof that native
Codex execution was selected; inspect the completed runtime result and
`/codex status`.

### JARVIS selects the normal OpenAI path instead of Codex

The Codex harness fails closed when the prepared provider route contains
request transport overrides, an incompatible runtime policy, or
unreproducible authentication. Check that:

- the requested provider is `codex` or an explicitly compatible `openai` route;
- no authored request transport override is present;
- subscription authentication is a prepared OAuth or token profile; and
- API-key authentication is a prepared API-key profile.

The `openai/gpt-*` prefix and a requested runtime id alone do not prove that
the Codex harness ran.

### The Codex app-server is rejected

JARVIS accepts managed Codex app-server version `0.153.4` and external
versions at or above `0.149.0`. Run:

```text
uv run jarvis doctor codex/managed-app-server
```

The doctor rejects missing, unverified, wrapper, or unsupported launchers.
Desktop binaries and official `@openai/codex` package entrypoints are
validated separately. Replace custom wrappers with an approved launcher or
install the managed Codex package.

### `/codex status` cannot connect

Check the following in the effective Codex plugin configuration:

- the Codex extension is enabled and allowed;
- `appServer.command` is a bare executable path, with arguments in
  `appServer.args`;
- WebSocket transport has `appServer.url`;
- remote WebSocket URLs have `appServer.authToken` or an equivalent identity
  header; and
- Unix transport uses a `unix://` URL and `homeScope: user`.

Then rerun `/codex status`. Do not use inline shell arguments in
`appServer.command`; the launch policy rejects them.

### Authentication falls back to an API-key path

JARVIS supports `CODEX_API_KEY`, but the Codex harness requires prepared auth
when a provider route declares a subscription or API-key requirement. Inspect
only redacted diagnostics showing the model, provider, selected harness, and
failure class. A valid subscription route should report a prepared OAuth or
token profile rather than an unprepared API-key fallback.

Never print `CODEX_API_KEY`, `OPENAI_API_KEY`, `CODEX_ACCESS_TOKEN`, bearer
headers, or OAuth credentials. Prepared-auth launches intentionally remove
credential variables from the child environment where required.

### WebSocket transport fails immediately

WebSocket transport is experimental. Check `appServer.url`, `authToken`,
headers, and the app-server protocol version. Remote WebSocket endpoints must
be identity-protected; unauthenticated remote endpoints are rejected. Prefer
managed stdio or the local Unix control socket for production use.

If the optional WebSocket dependency is missing, install the project-managed
dependencies with `uv sync`; do not add an ad-hoc runtime fallback.

### The app-server uses too much memory

The Codex app-server is a separate child process. Node or Python heap settings
for the JARVIS host do not cap the Codex child. Inspect host/container memory
and native Codex thread fan-out first. Reduce native concurrency in Codex's
own app-server configuration before increasing the JARVIS process limit.

JARVIS does not currently implement OpenClaw's shared-client idle-thread cache
or its 30-minute native thread eviction policy. Do not apply OpenClaw cache
limits to JARVIS and assume they take effect.

### Computer Use is installed but tools do not run

Run:

```text
/codex computer-use status
```

The status machine checks marketplace discovery, plugin installation and
enablement, MCP exposure, and a live `list_apps` probe. If strict readiness is
enabled, a failed live test blocks startup. Otherwise the result includes a
compatibility warning. Re-run `/codex computer-use install` only as an
owner/admin and only after verifying the marketplace configuration.

### Native shell or patch tools fail with a hook-relay error

JARVIS does not currently expose OpenClaw's native hook relay registration
surface. A hook-relay error is therefore an integration/runtime boundary
failure, not an ACP or provider failure. Start a fresh JARVIS session and
restart the Codex app-server; then rerun `/codex status` before retrying a
native tool call. If the error returns, collect a redacted doctor and
transport diagnostic for the owning Gateway/runtime integration.

### Codex plugin state or bindings appear stale

Codex binding, model, fast-mode, and permissions state is stored in the
canonical shared SQLite database. Check `JARVIS_STATE_DIR` and restart the
host after changing process-stable plugin metadata. Do not edit JSON sidecars
or manually duplicate binding state. Use `/codex binding`, `/codex detach`,
and `/codex bind <thread-id>` to repair an operator-owned binding.

### Scheduled Codex execution is denied

Scheduled native Codex turns require a Gateway-provided authority grant. The
provider boundary rejects scheduled execution without an explicit grant and
rejects mismatched provider/model/app/plugin inventory snapshots. This is
intentional fail-closed behavior. Repair the Gateway scheduling authority and
snapshot; do not bypass the check inside the Codex extension.

### A non-Codex model uses the Codex harness

The harness only supports declared `codex` or compatible `openai` routes. If a
non-Codex route is selected unexpectedly, inspect the prepared model provider
route and runtime policy. Unsupported overrides and authentication shapes must
fall back or fail closed; they must not be silently coerced into Codex.

## OpenClaw-only items

The following OpenClaw troubleshooting actions are not JARVIS commands and
must not be copied into JARVIS runbooks as if they worked:

- `openclaw doctor --fix` legacy model-ref migration;
- OpenClaw hook-relay registration recovery;
- OpenClaw's native 64-thread idle subscription cache;
- OpenClaw marketplace discovery cache invalidation and plugin metadata cache
  controls; and
- OpenClaw-specific `openclaw.json` configuration paths.

Use the JARVIS doctor contracts, canonical SQLite state, and `/codex` command
surface instead.
