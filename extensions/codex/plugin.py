"""Codex plugin entry definition.

OpenClaw parity: mirrors `extensions/codex/index.ts` entry point.

Registration sequence (matching index.ts lines 79-418):
 1. Set managed plugin root
 2. Config closures (current config + live plugin config resolution)
 3. Desktop generation service
 4. Process reaper service
 5. (websocket) Connection health service
 6. Lazy binding + managed-thread state stores
 7. CLI metadata registration
 8. App-server config factory (supervision options resolver)
 9. (sessionCatalog.enabled) Session catalog runtime + node host commands
10. Session catalog node invoke policies
11. (supervision.enabled) Supervision tools (owner-only)
12. Agent harness + native compaction
13. Media understanding provider
14. Web search provider
15. Migration provider
16. codex_threads tool + metadata
17. codex_plugins tool + metadata
18. CLI session node host commands + invoke policies
19. Node exec server command + invoke policy
20. /codex command
21. inbound_claim event handler
22. conversation_binding_resolved handler
23. session_end handler (with cross-key handoff guard)
"""

from __future__ import annotations

from typing import Any

from jarvis_sdk import (
    PluginApi,
    define_plugin_entry,
)

from extensions.codex.harness import (
    CODEX_HARNESS_ID,
    CODEX_HARNESS_LABEL,
    create_codex_app_server_agent_harness,
)
from extensions.codex.src.app_server.config import read_codex_plugin_config
from extensions.codex.src.app_server.managed_binary import set_managed_codex_plugin_root
from extensions.codex.src.conversation_binding_hooks import (
    handle_codex_conversation_binding_resolved,
    handle_codex_conversation_inbound_claim,
)

from extensions.codex.src.native_plugin_tool import create_codex_plugins_tool

from extensions.codex.src.node_exec_server import (
    create_codex_node_exec_server_command,
    create_codex_node_exec_server_invoke_policy,
)
from extensions.codex.src.session_catalog import (
    codex_session_catalog_runtime_register,
    create_codex_session_catalog_control,
    create_codex_session_catalog_node_host_commands,
    create_codex_session_catalog_node_invoke_policies,
)
from extensions.codex.src.supervision_tools import (
    CODEX_SUPERVISION_COMPAT_TOOL_NAMES,
    create_codex_supervision_tools,
)


# Sessions ended for these reasons retire their Codex thread binding.
# Mirrors OpenClaw's `ENDED_SESSION_REASONS` (index.ts:70).
_ENDED_SESSION_REASONS: frozenset[str] = frozenset({"new", "reset", "idle", "daily"})


def _register(api: PluginApi) -> None:  # noqa: C901  (intentionally long — mirrors index.ts)
    # -----------------------------------------------------------------------
    # 1. Set managed plugin root so managed_binary can find the bundled codex
    #    binary relative to this extension's installed location.
    # -----------------------------------------------------------------------
    set_managed_codex_plugin_root(getattr(api, "root_dir", None))

    # Register the reload noop prefixes (mirrors index.ts:76-78).
    # codexPlugins is expensive to re-read live; suppress that path.
    if hasattr(api, "register_reload"):
        api.register_reload(_reload_config)

    # -----------------------------------------------------------------------
    # 2. Config-resolution closures (mirrors index.ts lines 83-114).
    #    resolve_current_config() reads the live gateway config snapshot.
    #    resolve_current_plugin_config() extracts the codex plugin sub-block
    #    using the same live-removal / startup-fallback logic as OpenClaw.
    # -----------------------------------------------------------------------
    def resolve_current_config() -> Any:
        runtime = getattr(api, "runtime", None)
        config_host = getattr(runtime, "config", None) if runtime else None
        current_fn = getattr(config_host, "current", None)
        if callable(current_fn):
            try:
                return current_fn()
            except Exception:
                pass
        return getattr(api, "config", None)

    def resolve_current_plugin_config() -> Any:
        live_config = resolve_current_config()
        # Try to extract codex config from the live config object
        if isinstance(live_config, dict):
            plugins = live_config.get("plugins", {})
            if isinstance(plugins, dict):
                entries = plugins.get("entries", {})
                if isinstance(entries, dict):
                    codex_entry = entries.get("codex", {})
                    if isinstance(codex_entry, dict):
                        cfg = codex_entry.get("config")
                        if cfg is not None:
                            return read_codex_plugin_config(cfg if isinstance(cfg, dict) else {})
        # Fall back to startup plugin config
        return read_codex_plugin_config(
            api.plugin_config if isinstance(api.plugin_config, dict) else {}
        )

    # -----------------------------------------------------------------------
    # 3. Desktop generation service (triggers shared-client retirement before
    #    a new Codex desktop generation is installed).
    # -----------------------------------------------------------------------
    try:
        from extensions.codex.src.app_server.desktop_generation import (  # noqa: PLC0415
            create_codex_desktop_generation_service,
            retire_shared_codex_app_server_clients_before_desktop_generation,
        )

        api.register_service(
            create_codex_desktop_generation_service(
                on_generation_change=retire_shared_codex_app_server_clients_before_desktop_generation,
            )
        )
    except ImportError:
        pass  # desktop generation service not yet ported; safe to skip

    # -----------------------------------------------------------------------
    # 4. Process reaper service (cleans up orphaned transport processes).
    # -----------------------------------------------------------------------
    try:
        from extensions.codex.src.app_server.transport_process_registration import (  # noqa: PLC0415
            create_codex_app_server_process_reaper_service,
        )

        api.register_service(create_codex_app_server_process_reaper_service())
    except ImportError:
        pass

    # -----------------------------------------------------------------------
    # 5. Websocket connection health service (only when transport=websocket).
    # -----------------------------------------------------------------------
    plugin_cfg_at_start = resolve_current_plugin_config()
    app_server_at_start = getattr(plugin_cfg_at_start, "app_server", None)
    if getattr(app_server_at_start, "transport", "stdio") == "websocket":
        try:
            from extensions.codex.src.app_server.connection_health import (  # noqa: PLC0415
                create_codex_app_server_connection_health_service,
            )

            api.register_service(
                create_codex_app_server_connection_health_service(
                    get_plugin_config=resolve_current_plugin_config,
                    get_runtime_config=resolve_current_config,
                )
            )
        except ImportError:
            pass

    # -----------------------------------------------------------------------
    # 6. Lazy binding state store + managed-thread state store.
    #    OpenClaw uses PluginStateSyncKeyedStore; JARVIS uses CodexConversationStore
    #    (SQLite-backed) or a plain dict as fallback.
    # -----------------------------------------------------------------------
    from extensions.codex.src.conversation_store import CodexConversationStore  # noqa: PLC0415

    _binding_store_instance: CodexConversationStore | None = None

    def _get_binding_store() -> CodexConversationStore:
        nonlocal _binding_store_instance
        if _binding_store_instance is None:
            _binding_store_instance = CodexConversationStore()
        return _binding_store_instance

    # Lazy proxy that opens the store on first operation (matches OpenClaw's
    # "base registration runtime deliberately rejects state access" comment).
    class _LazyBindingStore:
        def read_binding(self, session_id: str) -> dict[str, Any] | None:
            return _get_binding_store().read_binding(session_id)

        def update_binding(self, session_id: str, value: dict[str, Any] | None) -> None:
            _get_binding_store().update_binding(session_id, value)

        def list_catalog_sessions(self, **kwargs: Any) -> list[dict[str, Any]]:
            # Catalog listing delegates to state reads; return empty until
            # a proper catalog-aware store is wired.
            return []

    binding_store = _LazyBindingStore()

    # -----------------------------------------------------------------------
    # 7. CLI metadata (adds --help / --version model introspection).
    # -----------------------------------------------------------------------
    try:
        from extensions.codex.src.cli_metadata import register_codex_cli_metadata  # noqa: PLC0415

        register_codex_cli_metadata(api)
    except ImportError:
        pass

    # -----------------------------------------------------------------------
    # 8. App-server config factory — produces the supervision runtime options
    #    resolver used by catalog control and supervision tools.
    # -----------------------------------------------------------------------
    def resolve_supervision_runtime_options(**kwargs: Any) -> Any:
        from extensions.codex.src.app_server.config import (  # noqa: PLC0415
            resolve_codex_app_server_runtime_options,
        )

        plugin_config_dict = (
            vars(resolve_current_plugin_config())
            if not isinstance(resolve_current_plugin_config(), dict)
            else resolve_current_plugin_config()
        )
        return resolve_codex_app_server_runtime_options(
            plugin_config_dict,
            **kwargs,
        )

    # -----------------------------------------------------------------------
    # 9. Session catalog (enabled by default; opt-out with
    #    sessionCatalog.enabled: false).
    # -----------------------------------------------------------------------
    catalog_cfg = getattr(plugin_cfg_at_start, "session_catalog", None)
    session_catalog_enabled = getattr(catalog_cfg, "enabled", True)
    session_catalog_control = create_codex_session_catalog_control(
        resolve_runtime_options=resolve_supervision_runtime_options,
        binding_store=binding_store,
        get_plugin_config=resolve_current_plugin_config,
        get_runtime_config=resolve_current_config,
    )
    if session_catalog_enabled:
        codex_session_catalog_runtime_register(
            api,
            resolve_runtime_options=resolve_supervision_runtime_options,
            binding_store=binding_store,
            control=session_catalog_control,
            get_plugin_config=resolve_current_plugin_config,
            get_runtime_config=resolve_current_config,
        )
        for command in create_codex_session_catalog_node_host_commands(
            session_catalog_control,
            {
                "get_plugin_config": resolve_current_plugin_config,
                "get_runtime_config": resolve_current_config,
                "resolve_runtime_options": resolve_supervision_runtime_options,
            },
            binding_store,
        ):
            api.register_node_host_command(command)

    # -----------------------------------------------------------------------
    # 10. Session catalog node invoke policies (always, not gated on enabled).
    # -----------------------------------------------------------------------
    for policy in create_codex_session_catalog_node_invoke_policies():
        api.register_node_invoke_policy(policy)

    # -----------------------------------------------------------------------
    # 11. Supervision tools — owner-only, gated on supervision.enabled.
    #     OpenClaw: index.ts:211-235.
    # -----------------------------------------------------------------------
    supervision_raw = getattr(plugin_cfg_at_start, "supervision", None)
    supervision_enabled = (
        isinstance(supervision_raw, dict) and supervision_raw.get("enabled") is True
    )
    if supervision_enabled:

        def _make_supervision_tools(context: Any) -> list[Any]:
            sender_is_owner = getattr(context, "sender_is_owner", False)
            if not sender_is_owner:
                return []
            runtime_cfg = resolve_current_config()
            if callable(getattr(context, "get_runtime_config", None)):
                runtime_cfg = context.get_runtime_config()
            elif getattr(context, "runtime_config", None) is not None:
                runtime_cfg = context.runtime_config

            def _get_cfg() -> Any:
                return resolve_current_plugin_config()

            return create_codex_supervision_tools(
                get_plugin_config=_get_cfg,
                get_runtime_config=lambda: runtime_cfg,
                resolve_runtime_options=resolve_supervision_runtime_options,
                sender_is_owner=sender_is_owner,
            )

        api.register_tool(
            _make_supervision_tools,
            names=list(CODEX_SUPERVISION_COMPAT_TOOL_NAMES),
        )

    # -----------------------------------------------------------------------
    # 12. Agent harness + native compaction.
    # -----------------------------------------------------------------------
    harness_options = {
        "binding_store": binding_store,
        "session_catalog_control_factory": session_catalog_control,
        "resolve_config": resolve_current_config,
        "resolve_plugin_config": resolve_current_plugin_config,
        "runtime": getattr(api, "runtime", None),
    }
    harness = create_codex_app_server_agent_harness(**harness_options)
    api.register_agent_harness(harness)

    # -----------------------------------------------------------------------
    # 13. Media understanding provider.
    # -----------------------------------------------------------------------
    try:
        from extensions.codex.src.media_understanding_provider import (  # noqa: PLC0415
            build_codex_media_understanding_provider,
        )

        api.register_media_understanding_provider(
            build_codex_media_understanding_provider(
                plugin_config=api.plugin_config,
            )
        )
    except ImportError:
        pass

    # -----------------------------------------------------------------------
    # 14. Web search provider.
    # -----------------------------------------------------------------------
    try:
        from extensions.codex.src.web_search import (  # noqa: PLC0415
            create_codex_web_search_provider,
        )

        api.register_web_search_provider(
            create_codex_web_search_provider(
                resolve_plugin_config=resolve_current_plugin_config,
            )
        )
    except (ImportError, AttributeError):
        pass

    # -----------------------------------------------------------------------
    # 15. Migration provider (jarvis doctor --fix support).
    # -----------------------------------------------------------------------
    try:
        from extensions.codex.src.migration.provider import (  # noqa: PLC0415
            build_codex_migration_provider,
        )

        api.register_migration_provider(
            build_codex_migration_provider(runtime=getattr(api, "runtime", None))
        )
    except ImportError:
        pass  # Migration provider not yet ported; skip gracefully.

    # -----------------------------------------------------------------------
    # 16. codex_threads tool + metadata.
    #     OpenClaw: index.ts:253-269.
    # -----------------------------------------------------------------------
    def _make_codex_threads_tool(context: Any) -> list[Any]:
        from extensions.codex.src.native_threads import codex_threads_enabled  # noqa: PLC0415

        plugin_config = resolve_current_plugin_config()
        is_owner = bool(getattr(context, "sender_is_owner", False))
        if not codex_threads_enabled(plugin_config, is_owner=is_owner):
            return []
        return [
            {
                "name": "codex_threads",
                "description": (
                    "List, search, read, fork, rename, archive, and restore native Codex threads "
                    "in the shared user Codex home."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": ["list", "read", "fork", "rename", "archive", "unarchive"],
                        },
                        "thread_id": {"type": "string"},
                        "search": {"type": "string"},
                        "limit": {"type": "integer", "minimum": 1, "maximum": 200},
                        "cursor": {"type": "string"},
                        "new_name": {"type": "string"},
                        "archived": {"type": "boolean"},
                    },
                    "required": ["action"],
                    "additionalProperties": False,
                },
                "_binding_store": binding_store,
                "_context": context,
                "_plugin_config": plugin_config,
            }
        ]

    api.register_tool(_make_codex_threads_tool, name="codex_threads")
    api.register_tool_metadata(
        tool_name="codex_threads",
        display_name="Codex Threads",
        description="Manage native Codex threads in the shared user Codex home.",
        risk="high",
        tags=["codex", "sessions"],
    )

    # -----------------------------------------------------------------------
    # 17. codex_plugins tool + metadata.
    #     OpenClaw: index.ts:270-285.
    # -----------------------------------------------------------------------
    def _make_codex_plugins_tool(context: Any) -> list[Any]:
        tool = create_codex_plugins_tool(
            get_plugin_config=resolve_current_plugin_config,
            context=context,
        )
        return [tool]

    api.register_tool(_make_codex_plugins_tool, name="codex_plugins")
    api.register_tool_metadata(
        tool_name="codex_plugins",
        display_name="Codex Plugins",
        description="Discover available Codex plugins without installing or enabling them.",
        risk="low",
        tags=["codex", "plugins", "discovery"],
    )

    # -----------------------------------------------------------------------
    # 18. CLI session node host commands + invoke policies.
    #     OpenClaw: index.ts:286-291.
    # -----------------------------------------------------------------------
    try:
        from extensions.codex.src.node_cli_sessions import (  # noqa: PLC0415
            create_codex_cli_session_node_host_commands,
            create_codex_cli_session_node_invoke_policies,
        )

        for cmd in create_codex_cli_session_node_host_commands():
            api.register_node_host_command(cmd)
        for policy in create_codex_cli_session_node_invoke_policies():
            api.register_node_invoke_policy(policy)
    except ImportError:
        pass

    # -----------------------------------------------------------------------
    # 19. Node exec server command + invoke policy.
    #     OpenClaw: index.ts:292-293.
    # -----------------------------------------------------------------------
    api.register_node_host_command(create_codex_node_exec_server_command())
    api.register_node_invoke_policy(create_codex_node_exec_server_invoke_policy())

    # -----------------------------------------------------------------------
    # 20. /codex command.
    #     OpenClaw: index.ts:294-363.
    # -----------------------------------------------------------------------
    try:
        from extensions.codex.src.commands import create_codex_command  # noqa: PLC0415

        api.register_command(
            create_codex_command(
                plugin_config=api.plugin_config,
                resolve_plugin_config=resolve_current_plugin_config,
                binding_store=binding_store,
            )
        )
    except (ImportError, TypeError):
        # create_codex_command may not yet accept these kwargs; degrade gracefully.
        try:
            from extensions.codex.src.commands import handle_codex_command  # noqa: PLC0415

            api.register_command({
                "name": "codex",
                "description": "Run Codex commands",
                "handler": handle_codex_command,
            })
        except ImportError:
            pass

    # -----------------------------------------------------------------------
    # 21. inbound_claim event handler.
    #     OpenClaw: index.ts:364-375.
    # -----------------------------------------------------------------------
    def _on_inbound_claim(event: Any, ctx: Any) -> None:
        handle_codex_conversation_inbound_claim(
            event if isinstance(event, dict) else vars(event) if hasattr(event, "__dict__") else {},
            ctx if isinstance(ctx, dict) else vars(ctx) if hasattr(ctx, "__dict__") else {},
            binding_store=binding_store,
            plugin_config=resolve_current_plugin_config(),
            config=resolve_current_config(),
        )

    api.register_agent_event_subscription("inbound_claim", _on_inbound_claim)

    # -----------------------------------------------------------------------
    # 22. conversation_binding_resolved handler.
    #     OpenClaw: index.ts:373-375.
    # -----------------------------------------------------------------------
    def _on_binding_resolved(event: Any) -> None:
        handle_codex_conversation_binding_resolved(
            event if isinstance(event, dict) else vars(event) if hasattr(event, "__dict__") else {},
            binding_store=binding_store,
        )

    api.register_conversation_binding_resolved_handler(_on_binding_resolved)

    # -----------------------------------------------------------------------
    # 23. session_end handler — retire binding, guarded by cross-key handoff.
    #     OpenClaw: index.ts:376-416.
    # -----------------------------------------------------------------------
    async def _on_session_end(event: Any, ctx: Any) -> None:
        reason = event.get("reason") if isinstance(event, dict) else getattr(event, "reason", None)
        if not reason or reason not in _ENDED_SESSION_REASONS:
            return

        # Extract session ids
        ev = event if isinstance(event, dict) else {}
        ct = ctx if isinstance(ctx, dict) else {}
        session_id = (ev.get("sessionId") or ct.get("sessionId") or "").strip()
        session_key = (ev.get("sessionKey") or ct.get("sessionKey") or "").strip()
        next_session_key = (ev.get("nextSessionKey") or "").strip()
        next_session_id = (ev.get("nextSessionId") or "").strip()

        # Cross-key handoff guard: a fork fires session_end on the parent with
        # a different nextSessionKey; that child owns its own binding, so skip.
        # OpenClaw: index.ts:390-394.
        if session_key and next_session_key and next_session_key != session_key:
            return

        # Same-id rollover guard: reset hooks reuse the session id.
        # OpenClaw: index.ts:396-398.
        if next_session_id and next_session_id == session_id:
            return

        # Retire the binding so the next fresh session starts clean.
        if session_id and hasattr(binding_store, "update_binding"):
            try:
                binding_store.update_binding(session_id, None)
            except Exception:
                pass

    api.register_agent_event_subscription("session_end", _on_session_end)


def _reload_config() -> dict[str, Any]:
    """Reload noop prefixes — mirrors index.ts:76-78."""
    return {
        "noop_prefixes": ["plugins.entries.codex.config.codexPlugins"],
    }


entry = define_plugin_entry(
    id=CODEX_HARNESS_ID,
    kind="infra",
    name=CODEX_HARNESS_LABEL,
    description=(
        "Codex app-server harness and native session supervision. "
        "Mirrors OpenClaw extensions/codex/index.ts."
    ),
    register=_register,
)

# Keep backward-compatible re-exports that other modules currently import.
from extensions.codex.harness import (  # noqa: E402
    CODEX_CONTEXT_ENGINE_HOST_CAPABILITIES,
    CODEX_TOOL_POLICY_SAFE_DENY_NAMES,
    CodexAgentHarness,
)
from extensions.codex.src.commands import handle_codex_command  # noqa: E402
from extensions.codex.src.conversation_store import CodexConversationStore  # noqa: E402
from extensions.codex.src.doctor import (  # noqa: E402
    CODEX_MANAGED_APP_SERVER_CHECK_ID,
    check_codex_managed_app_server,
)
from extensions.codex.src.node_exec_server import (  # noqa: E402
    CODEX_NODE_EXEC_SERVER_CAPABILITY,
    CODEX_NODE_EXEC_SERVER_COMMAND,
)


# ---------------------------------------------------------------------------
# Backward-compat shim: CodexProvider
# Tests and callers that used ``CodexProvider().complete(...)`` previously
# relied on this class.  Keep it as a lightweight delegating shim so existing
# tests continue to pass while the plugin entry is now ``define_plugin_entry``.
# ---------------------------------------------------------------------------


class CodexProvider:
    """Lightweight compat shim for direct-call tests.

    Real completion goes through the ``define_plugin_entry`` harness at
    runtime; this shim exists only for the injected-transport test path
    where ``request_fn`` is passed explicitly.
    """

    id: str = "codex"

    async def complete(self, messages: list[Any], **kwargs: Any) -> Any:  # type: ignore[return]
        from jarvis_sdk import Err, Ok  # noqa: PLC0415
        from extensions.codex.src.execution_authority import check_codex_execution_authority  # noqa: PLC0415
        from extensions.codex.src.turn import complete_codex_turn  # noqa: PLC0415

        authorized, reason = check_codex_execution_authority(
            scheduled=kwargs.get("scheduled") is True,
            authority=kwargs.get("scheduled_authority"),
            inventory_snapshot=kwargs.get("inventory_snapshot"),
            expected_inventory_snapshot=kwargs.get("expected_inventory_snapshot"),
        )
        if not authorized:
            return Err(reason or "Codex execution is not authorized", code="forbidden")

        request = kwargs.get("request_fn")
        if not callable(request):
            return Err("request_fn is required for compat shim", code="unavailable")
        try:
            text = await complete_codex_turn(
                messages,
                request,
                thread_id=kwargs.get("thread_id"),
                model=kwargs.get("model"),
                runtime_options=kwargs.get("runtime_options"),
            )
        except Exception as exc:
            return Err(f"Codex turn failed: {exc}", code="provider_error")
        return Ok(text)


codex_provider = CodexProvider()


__all__ = [
    # Entry
    "entry",
    # Harness
    "CODEX_CONTEXT_ENGINE_HOST_CAPABILITIES",
    "CODEX_HARNESS_ID",
    "CODEX_HARNESS_LABEL",
    "CODEX_TOOL_POLICY_SAFE_DENY_NAMES",
    "CodexAgentHarness",
    "create_codex_app_server_agent_harness",
    # Commands
    "handle_codex_command",
    # Doctor
    "CODEX_MANAGED_APP_SERVER_CHECK_ID",
    "check_codex_managed_app_server",
    # Store
    "CodexConversationStore",
    # Node exec server
    "CODEX_NODE_EXEC_SERVER_CAPABILITY",
    "CODEX_NODE_EXEC_SERVER_COMMAND",
    "create_codex_node_exec_server_command",
    "create_codex_node_exec_server_invoke_policy",
    # Supervision
    "CODEX_SUPERVISION_COMPAT_TOOL_NAMES",
    "create_codex_supervision_tools",
]
