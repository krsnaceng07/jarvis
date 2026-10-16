# Native Codex Plugins

JARVIS native Codex plugin support keeps plugin calls inside the Codex
app-server thread. It does not translate Codex apps into synthetic dynamic
tools. Codex owns native app/MCP execution; JARVIS owns policy, inventory
validation, and the restrictive thread configuration.

## Requirements

- The active runtime must be the native Codex harness.
- The Codex extension must be enabled.
- `codexPlugins.enabled` must be `true`.
- The app-server must meet the managed version floor (`0.149.0` or newer).
- The target app-server must return installed plugin and app inventory.
- Each admitted app must have an exact configured plugin identity and a stable
  app id present in the current `app/installed` snapshot.

`codexPlugins` has no effect on normal OpenAI provider turns, ACP bindings, or
other harnesses. Those paths do not create a native Codex thread.

## Configuration

```json
{
  "codexPlugins": {
    "enabled": true,
    "allow_destructive_actions": "ask",
    "plugins": {
      "security-review@company-tools": {
        "enabled": true,
        "marketplaceName": "company-tools",
        "pluginName": "security-review"
      }
    }
  }
}
```

Marketplace-qualified identities are preferred. An unqualified config key is
accepted only when the explicit `marketplaceName` and `pluginName` fields
identify the plugin.

## Runtime pipeline

For a new native Codex thread, JARVIS performs this read-only sequence:

1. `plugin/installed` reads the current installed plugin snapshot.
2. `plugin/read` reads details for the exact configured plugin identity.
3. `app/installed` reads the current app inventory.
4. Only exact app ids owned by the configured plugin and present in the app
   snapshot are admitted.
5. JARVIS sends a restrictive `config.apps` patch to `thread/start`.

The default app policy is deny-all: `_default` is disabled and open-world app
access is disabled. Missing, stale, ambiguous, disabled, or failed inventory
never grants app access. The native Codex app-server remains authoritative for
its own account, marketplace, connector, and permission rules.

## Chat management

The reserved command surface is:

```text
/codex plugins
/codex plugins list
/codex plugins available
/codex plugins install <plugin>@<marketplace>
/codex plugins enable <name>
/codex plugins disable <name>
```

`install`, `enable`, and `disable` require an owner or `operator.admin` host
callback. Installation and policy mutation are intentionally not performed by
the model's dynamic tool layer.

## Scheduled runs

Scheduled Codex execution requires Gateway authority. The stored authority
must match the current provider, model, app-server, and plugin inventory facts.
Scheduled runs cannot gain new app ids, broader destructive policy, or access
through another runtime/account. A mismatch fails before app execution and
requires a fresh authenticated owner authorization.

## Troubleshooting

**No plugin apps appear:** verify `/codex plugins list`, then inspect the
app-server responses for `plugin/installed`, `plugin/read`, and
`app/installed`. JARVIS hides apps when any exact ownership or readiness fact
is missing.

**The plugin is installed but disabled:** enable it in the Codex account or
use the owner/admin `/codex plugins enable <name>` path, then start a new Codex
conversation so the restrictive thread config is rebuilt.

**Destructive actions are denied:** check the global and per-plugin
`allow_destructive_actions` policy. `false` denies them; `true`, `auto`, and
`ask` admit them only after exact ownership and native Codex policy checks.

**Scheduled app access is denied:** repair the Gateway authority grant or
inventory snapshot. Do not bypass the provider boundary or add synthetic
`codex_plugin_*` tools.

JARVIS does not implement OpenClaw's Codex migration CLI, one-hour process-local
app cache, connected-account `allow_all_plugins` admission, or native plugin
approval bridge yet. Those are separate Gateway/app-server ownership surfaces;
unsupported OpenClaw commands must not be copied into JARVIS runbooks.
