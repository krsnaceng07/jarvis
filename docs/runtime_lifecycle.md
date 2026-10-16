# JARVIS Runtime Lifecycle Reference

This document outlines the operational lifecycle of JARVIS, including startup, execution, shutdown, and recovery.

---

## 1. Lifecycle Phases

1. **Host Boot**: Initializes logging, loads configuration, opens canonical SQLite databases.
2. **Plugin Discovery**: Scans `extensions/` for `openclaw.plugin.json`, validates schemas, loads plugins into `PluginRegistry`.
3. **Channel Supervisor Startup**: Discovers all enabled channel accounts, runs account preflight, boots listeners concurrently.
4. **Steady-State Turn Loop**: Listens for inbound messages, executes 5-stage turn runner, interacts with model and tools, delivers outbound responses.
5. **Graceful Shutdown**: On `SIGINT`/`SIGTERM` or app exit, notifies sidecars, waits for active turns to settle (drain timeout), closes database transactions, releases polling leases.
6. **Crash & Restart Recovery**: Reconnects to SQLite store, identifies interrupted or orphaned session bindings, and resumes continuity.
