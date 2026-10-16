# Codex Provider Extension (JARVIS)

Minimum scaffold matching the OpenClaw `extensions/codex/`
shape. The OpenClaw source is 150 files; this
Python port ships a focused subset.

## Parity status (vs `openclaw-main/extensions/codex/`)

| OpenClaw | JARVIS | Notes |
|---|---|---|
| `index.ts` (entrypoint) | `__init__.py` + `plugin.py` | stub entry |
| `ProviderPlugin` descriptor | `CodexProvider` dataclass | shape equivalent |
| App-server request client | `src/app_server/transport.py` | stdio + Unix transports; injectable experimental WebSocket connector |
| Model catalog | `default_model` + `list_models()` | Implemented |

## Auth

API key: `CODEX_API_KEY` (read at provider init time).

## Base URL

`https://api.openai.com/v1` (OpenAI-compatible).

The minimum-scaffold is loadable + discoverable; the full
streaming + tool-use surface lands in Phase 5.16.

## Remote-exec guardrails (ported)

- `src/node_exec_server_runtime.py` — HTTP credential gate
  (`reject_credentialed_node_http_request`, `-32602` rejection),
  `process/start` env sanitize. Parity:
  `openclaw-main/extensions/codex/src/app-server/sandbox-exec-server-node-relay.ts`
  (credential section). Sensitivity oracle is
  `jarvis_sdk.memory_host_error_utils.redact_sensitive_text`
  (no tool-payload redactor seam yet); header/field patterns verbatim.
- `src/app_server/placement.py` — `is_remote_exec_placement_sandbox` /
  `is_paired_node_remote_exec_placement_sandbox` (config-parsing.ts).
  `/btw` blocks only paired-device placement (side-question.ts).

Not yet ported (need Gateway-owned placement/approval rows or transport):
standing-grant runtime, `sessions.dispatch(deviceId)`, nodes platform
matrices, Crabbox remote-exec runtime, relay pump, spawn-time strict env
allowlist, turn dispatch (effort payload, posture mapping). Runtime inventory
snapshot validation and scheduled authority enforcement are implemented at
the provider boundary in `src/execution_authority.py`.

`/codex` command tree (`src/commands.py` + `command_args.py`,
`command_actions.py`, `command_authorization.py`,
`conversation_control.py`): full verb list, arg parsers (bind/resume/
sessions/fast/permissions), owner/admin gates, usage errors, native control
RPCs for threads, goals, stop, steer, review, account, MCP, skills, and
plugins, plus honest unavailable terminals for persistence-owned flows.
Bind/resume/detach verify idle native threads and use a host-owned binding
update callback. `CodexConversationStore` provides canonical SQLite
binding/session state and is wired automatically when a command context has a
session id. Menu pickers and full diagnostics cooldown/scope handling still
need Gateway-owned integration.

Ported app-server startup policy (`src/app_server/`): NODE_OPTIONS
attestation (`node_options.py`, runtime-artifact.ts), launch config
helpers (`launch_policy.py`: clearEnv, args lexer, inline-args guard,
policy mode, posture/serviceTier/headers normalizers), env overrides +
`clearEnv`/`mode`/`homes`/posture/`serviceTier`/`codeModeOnly`/`headers`/
`remoteWorkspaceRoot`/`defaultWorkspaceDir` fields (`config.py`),
launch-config doctor gates (`doctor.py`: inline-args,
homes-requires-stdio, NODE_OPTIONS gate on the version subprocess).

Parsed and applied by the local app-server transport: posture fields
(`approvalPolicy` incl. `on-failure` alias, `sandbox`,
`approvalsReviewer`, `serviceTier` incl. legacy `fast`, `codeModeOnly`,
`headers`, `remoteWorkspaceRoot` canonical placement,
`defaultWorkspaceDir`), `networkProxy` validated shape, `codexPlugins`
passthrough, `supervision` endpoint shapes, posture env fallbacks.
Doctor reports retired `approvalPolicy: "untrusted"`.

Gateway still owns creation and delivery of the authority grant and inventory
snapshot; Codex validates both fail-closed when supplied.

Native Codex plugin support is implemented as an OpenClaw-aligned read-only
inventory preflight: `plugin/installed`, exact `plugin/read`, and
`app/installed` are resolved before `thread/start`. Only ownership-proven app
ids enter the restrictive `config.apps` patch; `_default` and open-world app
access remain disabled otherwise. Policy normalization lives in
`src/plugin_policy.py`, inventory reads in `src/plugin_inventory.py`, and the
thread pipeline is wired through `src/turn.py`.
