# Codex Provider Extension (JARVIS)

Minimum scaffold matching the OpenClaw `extensions/codex/`
shape. The OpenClaw source is 150 files; this
Python port ships a focused subset.

## Parity status (vs `openclaw-main/extensions/codex/`)

| OpenClaw | JARVIS | Notes |
|---|---|---|
| `index.ts` (entrypoint) | `__init__.py` + `plugin.py` | stub entry |
| `ProviderPlugin` descriptor | `CodexProvider` dataclass | shape equivalent |
| Streaming client | deferred | Phase 5.16 |
| Model catalog | `default_model` + `list_models()` stub | Phase 5.16 |

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
allowlist, turn dispatch (effort payload, posture mapping, app/plugin
snapshot checks), launcher binary attestation.

`/codex` command tree (`src/commands.py` + `command_args.py`,
`command_actions.py`, `command_authorization.py`,
`conversation_control.py`): full verb list, arg parsers (bind/resume/
sessions/fast/permissions), owner/admin gates, usage errors, and honest
unavailable terminals naming the missing backend. Working verbs unchanged
(help/btw/models/binding/computer-use/status). Menu pickers need channel
UI; session/thread stores and app-server turns need transport.

Ported app-server startup policy (`src/app_server/`): NODE_OPTIONS
attestation (`node_options.py`, runtime-artifact.ts), launch config
helpers (`launch_policy.py`: clearEnv, args lexer, inline-args guard,
policy mode, posture/serviceTier/headers normalizers), env overrides +
`clearEnv`/`mode`/`homes`/posture/`serviceTier`/`codeModeOnly`/`headers`/
`remoteWorkspaceRoot`/`defaultWorkspaceDir` fields (`config.py`),
launch-config doctor gates (`doctor.py`: inline-args,
homes-requires-stdio, NODE_OPTIONS gate on the version subprocess).

Parsed but inert until turn transport exists: posture fields
(`approvalPolicy` incl. `on-failure` alias, `sandbox`,
`approvalsReviewer`, `serviceTier` incl. legacy `fast`, `codeModeOnly`,
`headers`, `remoteWorkspaceRoot` canonical placement,
`defaultWorkspaceDir`), `networkProxy` validated shape, `codexPlugins`
passthrough, `supervision` endpoint shapes, posture env fallbacks.
Doctor reports retired `approvalPolicy: "untrusted"`.

Not yet ported (need turn transport or app-server connections):
WebSocket heartbeat/backoff, posture→Guardian runtime mapping,
networkProxy profile generation, SecretInput resolution, launcher binary
attestation, app/plugin inventory snapshot checks, scheduled authority.
