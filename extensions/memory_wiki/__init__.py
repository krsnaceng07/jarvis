"""memory_wiki — JARVIS persistent wiki compiler + Obsidian-friendly vault.

OpenClaw parity: this is the Phase 4.3a foundation
scaffold. The plugin entry point is provided by
``index.py`` (Phase 4.3g) which calls
``register_memory_wiki(api)``. Phase 4.3a ships the
type / time / log / source-path / vault-page-write
primitives so subsequent sub-phases can build on a
shared surface.

This file is intentionally slim: it just re-exports
the public foundation surface for the host's
``extensions.memory_wiki`` import and registers the
plugin via ``define_plugin_entry`` so the host can
load it. The full ``register`` callback (with the
gateway methods, tool registrations, prompt section,
and lifecycle service) is wired in Phase 4.3g.
"""

from __future__ import annotations

import logging
from typing import Any

from jarvis_sdk import PluginApi, define_plugin_entry

from . import (
    apply as _apply,
    bridge as _bridge,
    chatgpt_import as _chatgpt_import,
    claim_health as _claim_health,
    compile_pages as _compile_pages,
    compile_pipeline as _compile_pipeline,
    compile_render as _compile_render,
    compiled_cache as _compiled_cache,
    config as _config,
    config_compat as _config_compat,
    corpus_supplement as _corpus_supplement,
    doctor_contract as _doctor_contract,
    import_insights as _import_insights,
    import_runs as _import_runs,
    import_runs_state as _import_runs_state,
    ingest as _ingest,
    lint as _lint,
    log as _log,
    markdown as _markdown,
    markdown_pages as _markdown_pages,
    memory_palace as _memory_palace,
    mutation_coordinator as _mutation_coordinator,
    obsidian as _obsidian,
    okf as _okf,
    prompt_section as _prompt_section,
    query as _query,
    setup_api as _setup_api,
    source_page_shared as _source_page_shared,
    source_path_shared as _source_path_shared,
    source_sync as _source_sync,
    source_sync_state as _source_sync_state,
    status as _status,
    time as _time,
    tool as _tool,
    unsafe_local as _unsafe_local,
    vault as _vault,
    vault_page_write as _vault_page_write,
    wiki_cli as _wiki_cli,
    wiki_page_summary as _wiki_page_summary,
)

_LOGGER = logging.getLogger("jarvis.extensions.memory_wiki")


def register_memory_wiki(api: PluginApi) -> None:  # noqa: PLR0915 — mirrors OpenClaw's exhaustive 11-section register body
    """Register the memory-wiki plugin with the host.

    Phase 4.3g-mr8 ships the **full**
    OpenClaw ``index.ts`` registration body:
    config + resolver + state stores +
    lifecycle service + prompt supplement
    + corpus supplement + gateway methods
    + 5 tools + CLI registration. The
    surface mirrors OpenClaw's
    ``register(api)`` body line-for-line so
    ``register_memory_wiki_setup``
    (Phase 4.3g-mr6) and the
    ``register_memory_wiki_doctor_contracts``
    (Phase 4.3g-mr7) become sibling
    plugin entries the host can load.

    Each ``register_*`` call is wrapped in a
    ``getattr(api, ...)`` + ``callable``
    guard so older hosts (that haven't
    wired every SDK surface) silently skip
    the missing calls instead of crashing.
    """
    logger = getattr(api, "logger", None)
    log_fn = getattr(logger, "info", None) if logger is not None else None
    if callable(log_fn):
        log_fn("memory-wiki: phase 4.3g-mr8 full entry loaded")

    # ── Config + resolver ─────────────────────────
    plugin_config = getattr(getattr(api, "ctx", None), "config", None)
    config = _config.resolve_memory_wiki_config(plugin_config)

    def _get_app_config() -> Any | None:
        runtime = getattr(api, "runtime", None)
        runtime_config = getattr(runtime, "config", None) if runtime is not None else None
        current = getattr(runtime_config, "current", None) if runtime_config else None
        if callable(current):
            try:
                return current()
            except Exception:
                return getattr(api, "config", None)
        return getattr(api, "config", None)

    app_config = _get_app_config()

    def _resolve_config(agent_id: str | None, app_config_arg: Any | None = None) -> Any:
        return _config.resolve_memory_wiki_agent_config(
            config=config,
            app_config=app_config_arg if app_config_arg is not None else app_config,
            agent_id=agent_id,
        )

    def _resolve_tool_context(agent_id: str | None) -> dict[str, Any] | None:
        if config.vault.scope == "agent" and not agent_id:
            configured_ids = _config.resolve_memory_wiki_configured_agent_ids(app_config)
            if len(configured_ids) > 1:
                # Context-free tool discovery
                # cannot safely choose one
                # agent's vault.
                return None
        return {
            "appConfig": app_config,
            "config": _resolve_config(agent_id, app_config),
        }

    # ── State stores ──────────────────────────────
    runtime = getattr(api, "runtime", None)
    state = getattr(runtime, "state", None) if runtime is not None else None
    open_keyed_store = getattr(state, "openKeyedStore", None) if state else None
    open_blob_store = getattr(state, "openBlobStore", None) if state else None

    if callable(open_keyed_store):
        _source_sync_state.configure_memory_wiki_source_sync_state_store(
            _source_sync_state.create_memory_wiki_source_sync_state_store(open_keyed_store)
        )
        _import_runs_state.configure_memory_wiki_import_run_state_store(
            _import_runs_state.create_memory_wiki_import_run_state_store(open_keyed_store)
        )

    # ── Lifecycle service (compiled-cache owner
    #    cleanup) ──────────────────────────────────
    if callable(open_blob_store):
        _compiled_cache.configure_memory_wiki_compiled_cache_store(
            _compiled_cache.create_memory_wiki_compiled_cache_store(
                open_blob_store,
            )
        )

    register_service = getattr(api, "register_service", None)
    if callable(register_service):

        def _start_compiled_cache_owner_cleanup() -> None:
            _run_compiled_cache_owner_cleanup(config, app_config)

        register_service(
            {
                "id": "memory-wiki-compiled-cache-owner-cleanup",
                "start": _start_compiled_cache_owner_cleanup,
            }
        )

    # ── Prompt supplement + preparation ──────────
    register_memory_supplement = getattr(api, "register_memory_prompt_supplement", None)
    if callable(register_memory_supplement):
        register_memory_supplement(_prompt_section.create_wiki_prompt_section_builder())

    register_memory_preparation = getattr(api, "register_memory_prompt_preparation", None)
    if callable(register_memory_preparation):
        register_memory_preparation(
            _prompt_section.create_wiki_prompt_section_preparer(
                config=config,
                resolve_config=_resolve_config,
            )
        )

    register_memory_corpus_supplement = getattr(api, "register_memory_corpus_supplement", None)
    if callable(register_memory_corpus_supplement):
        register_memory_corpus_supplement(
            _corpus_supplement.create_wiki_corpus_supplement(
                resolve_config=_resolve_config,
                get_app_config=_get_app_config,
            )
        )

    # ── Gateway methods ───────────────────────────
    register_gateway_methods = getattr(api, "register_gateway_methods", None)
    if callable(register_gateway_methods):
        register_gateway_methods(
            {
                "api": api,
                "config": config,
                "appConfig": getattr(api, "config", None),
                "getAppConfig": _get_app_config,
                "resolveConfig": _resolve_config,
            }
        )

    # ── 5 wiki tools ──────────────────────────────
    register_tool = getattr(api, "register_tool", None)
    if callable(register_tool):

        def _status_tool_factory(ctx: Any) -> Any | None:
            resolved = _resolve_tool_context(getattr(ctx, "agent_id", None))
            if resolved is None:
                return None
            memory_context = _tool.WikiToolMemoryContext(
                agent_id=resolved["config"].agent_id or getattr(ctx, "agent_id", None),
                agent_session_key=getattr(ctx, "session_key", None),
                sandboxed=bool(getattr(ctx, "sandboxed", False)),
            )
            return _tool.create_wiki_status_tool(
                resolved["config"],
                resolved["appConfig"],
                memory_context=memory_context,
            )

        register_tool(_status_tool_factory, {"name": "wiki_status"})

        def _lint_tool_factory(ctx: Any) -> Any | None:
            resolved = _resolve_tool_context(getattr(ctx, "agent_id", None))
            if resolved is None:
                return None
            return _tool.create_wiki_lint_tool(resolved["config"], resolved["appConfig"])

        register_tool(_lint_tool_factory, {"name": "wiki_lint"})

        def _apply_tool_factory(ctx: Any) -> Any | None:
            resolved = _resolve_tool_context(getattr(ctx, "agent_id", None))
            if resolved is None:
                return None
            return _tool.create_wiki_apply_tool(resolved["config"], resolved["appConfig"])

        register_tool(_apply_tool_factory, {"name": "wiki_apply"})

        def _search_tool_factory(ctx: Any) -> Any | None:
            resolved = _resolve_tool_context(getattr(ctx, "agent_id", None))
            if resolved is None:
                return None
            memory_context = _tool.WikiToolMemoryContext(
                agent_id=resolved["config"].agent_id or getattr(ctx, "agent_id", None),
                agent_session_key=getattr(ctx, "session_key", None),
                sandboxed=bool(getattr(ctx, "sandboxed", False)),
            )
            return _tool.create_wiki_search_tool(
                resolved["config"],
                resolved["appConfig"],
                memory_context=memory_context,
            )

        register_tool(_search_tool_factory, {"name": "wiki_search"})

        def _get_tool_factory(ctx: Any) -> Any | None:
            resolved = _resolve_tool_context(getattr(ctx, "agent_id", None))
            if resolved is None:
                return None
            memory_context = _tool.WikiToolMemoryContext(
                agent_id=resolved["config"].agent_id or getattr(ctx, "agent_id", None),
                agent_session_key=getattr(ctx, "session_key", None),
                sandboxed=bool(getattr(ctx, "sandboxed", False)),
            )
            return _tool.create_wiki_get_tool(
                resolved["config"],
                resolved["appConfig"],
                memory_context=memory_context,
            )

        register_tool(_get_tool_factory, {"name": "wiki_get"})

    # ── CLI registration ──────────────────────────
    register_cli = getattr(api, "register_cli", None)
    if callable(register_cli):

        def _register_wiki(ctx: Any) -> None:
            """CLI registrar — matches OpenClaw's ``({ program }) => ...`` shape.

            Accepts the OpenClaw context dict ``{program, parentPath,
            config, workspaceDir, logger}`` and destructures ``program``.
            The host invokes us with the root argparse parser (or a
            subparsers container for hosts that pre-register top-level
            commands) so we can call ``add_parser`` / ``add_subparsers``
            on it — same as OpenClaw's ``registerWikiCli`` does.
            """
            if isinstance(ctx, dict):
                program = ctx.get("program")
            else:
                # Backwards-compat: the host may pass the parser directly
                # (older wiring).
                program = ctx
            if program is None:
                # Older host with no program surface; skip CLI wiring.
                return
            _wiki_cli.register_wiki_cli(
                program,
                _wiki_cli.MemoryWikiCliRegistration(
                    config=config,
                    resolve_config=_resolve_config,
                    get_app_config=_get_app_config,
                ),
            )

        register_cli(
            _register_wiki,
            descriptors=[
                {
                    "name": "wiki",
                    "description": "Inspect and initialize the memory wiki vault",
                    "hasSubcommands": True,
                }
            ],
        )

    # ── Doctor contracts (Phase 4.3g-mr7) ─────────
    register_memory_wiki_doctor_contracts(api)

    # ── Setup API (Phase 4.3g-mr6) ──────────────────
    register_memory_wiki_setup(api)


def _safe_log_warn(logger: Any, message: str) -> None:
    """Log a warning through ``logger`` if it
    exposes a ``warn`` method, otherwise
    silently drop the message.
    """
    if logger is None:
        return
    log_fn = getattr(logger, "warn", None)
    if callable(log_fn):
        log_fn(message)


def _run_compiled_cache_owner_cleanup(config: Any, app_config: Any) -> None:
    """Reconcile the per-vault compiled-cache
    owner set on plugin startup.

    Mirrors OpenClaw's
    ``api.registerService({...})`` ``start``
    body: every configured vault has its
    compiled-cache owner activated, then
    the previous trusted owners are pruned
    + the keyed / blob stores delete the
    matching keys.

    The Python port runs the body
    synchronously (the host's compiled-cache
    store APIs are sync) and the lifecycle
    service's ``start`` callback wraps
    ``asyncio.run`` on the caller's side if
    it needs an awaitable.
    """
    from . import compiled_cache as _cc

    active_configs: list[Any] = []
    if config.vault.scope == "global":
        active_configs.append(config)
    else:
        for agent_id in _config.resolve_memory_wiki_configured_agent_ids(app_config):
            active_configs.append(
                _config.resolve_memory_wiki_agent_config(
                    config=config, app_config=app_config, agent_id=agent_id
                )
            )

    # Clear every previously trusted
    # owner before fallible vault reads. A
    # failed lifecycle refresh must leave
    # prompt preparation closed, not
    # stale-but-active.
    _cc.deactivate_memory_wiki_compiled_cache_owners_except(set())

    prepared_owners: list[tuple[Any, dict[str, Any]]] = []
    for active_config in active_configs:
        identity = _load_configured_vault_identity(active_config.vault.path)
        if identity is not None:
            prepared_owners.append((active_config, identity))

    active_owner_ids: set[str] = set()
    try:
        for active_config, identity in prepared_owners:
            _cc.activate_memory_wiki_compiled_cache_owner(
                active_config,
                identity["vaultGeneration"],
                identity["compiledCachePublicationId"],
            )
            _cc.reconcile_memory_wiki_compiled_cache_owner(
                active_config,
                lambda active_config=active_config: _load_validated_identity(
                    active_config.vault.path
                ),
            )
            active_owner_ids.add(_cc.resolve_memory_wiki_compiled_cache_owner_id(active_config))
    except Exception:
        _cc.deactivate_memory_wiki_compiled_cache_owners_except(set())
        raise

    _cc.deactivate_memory_wiki_compiled_cache_owners_except(active_owner_ids)
    store = getattr(_cc, "_configured_store", None)
    if store is not None and hasattr(store, "delete_owners_except"):
        import contextlib

        with contextlib.suppress(Exception):
            store.delete_owners_except(active_owner_ids)


def _load_configured_vault_identity(vault_root: str) -> dict[str, Any] | None:
    """Load a vault's identity from the
    log + scaffold files. Mirrors
    OpenClaw's ``loadConfiguredVaultIdentity``.
    """
    from .log import load_memory_wiki_validated_vault_identity

    identity = load_memory_wiki_validated_vault_identity(vault_root)
    if identity.vault_generation:
        return {
            "vaultGeneration": identity.vault_generation,
            "compiledCachePublicationId": identity.compiled_cache_publication_id,
        }
    return None


def _load_validated_identity(vault_root: str) -> dict[str, Any]:
    """Sync wrapper around
    ``load_memory_wiki_validated_vault_identity``
    so the compiled-cache owner
    reconciliation loop can pass it to
    :func:`reconcile_memory_wiki_compiled_cache_owner`.
    """
    from .log import load_memory_wiki_validated_vault_identity

    identity = load_memory_wiki_validated_vault_identity(vault_root)
    return {
        "vaultGeneration": identity.vault_generation,
        "compiledCachePublicationId": identity.compiled_cache_publication_id,
    }


# ``define_plugin_entry`` is the SDK helper that
# builds the ``.entry`` symbol the host looks for
# when it imports the extension. Phase 4.3g-mr8
# ships the full surface (lifecycle service +
# prompt supplement + corpus supplement +
# gateway + 5 tools + CLI + doctor contracts
# + setup API).
entry = define_plugin_entry(
    id="memory_wiki",
    kind="memory",
    name="Memory Wiki",
    description=("Persistent wiki compiler and Obsidian-friendly " "knowledge vault for JARVIS."),
    activation="on_startup",
    register=register_memory_wiki,
)


# Public re-exports (the ``extensions.memory_wiki``
# surface that other extensions / tests can import).
__all__ = [
    "entry",
    "register_memory_wiki",
    # Foundation surface re-exported so callers can
    # ``from extensions.memory_wiki import resolve_artifact_key``
    # without reaching into the submodules.
    "resolve_artifact_key",
    "resolve_memory_wiki_timestamp",
    "append_memory_wiki_log",
    "ensure_memory_wiki_vault_generation",
    "load_memory_wiki_vault_identity",
    "load_memory_wiki_validated_vault_identity",
    "resolve_memory_wiki_vault_source_generation",
    "write_guarded_vault_page",
    # Config surface (Phase 4.3b).
    "memory_wiki_config_schema",
    "resolve_memory_wiki_config",
    "resolve_memory_wiki_agent_config",
    "resolve_memory_wiki_configured_agent_ids",
    "normalize_compatibility_config",
    # Vault init (Phase 4.3c).
    "initialize_memory_wiki_vault",
    "InitializeMemoryWikiVaultResult",
    "WIKI_VAULT_DIRECTORIES",
    "WIKI_VAULT_SCAFFOLD",
    # Markdown foundation (Phase 4.3c).
    "WIKI_PAGE_KINDS",
    "WIKI_RAW_SOURCE_MARKER",
    "WIKI_RELATED_START_MARKER",
    "WIKI_RELATED_END_MARKER",
    "parse_wiki_frontmatter",
    "replace_managed_markdown_block",
    "with_trailing_newline",
    # Markdown pages (Phase 4.3c-mr2).
    "WikiClaim",
    "WikiClaimEvidence",
    "WikiPersonCard",
    "WikiRelationship",
    "WikiPageFrontmatterError",
    "normalize_wiki_claims",
    "normalize_wiki_person_card",
    "normalize_wiki_relationships",
    "normalize_source_ids",
    "slugify_wiki_segment",
    "slugify_wiki_page_stem",
    "create_wiki_page_filename",
    "render_wiki_markdown",
    "extract_title_from_markdown",
    "extract_wiki_links",
    # Mutation coordinator (Phase 4.3d).
    "with_memory_wiki_vault_mutation",
    "resolve_memory_wiki_vault_mutation_key",
    # Prompt section (Phase 4.3f-mr6).
    "DIGEST_MAX_CLAIMS_PER_PAGE",
    "DIGEST_MAX_PAGES",
    "MemoryPromptSectionBuilder",
    "MemoryPromptSectionParams",
    "MemoryPromptSectionPreparer",
    "build_digest_prompt_section",
    "build_wiki_tool_guidance",
    "create_wiki_prompt_section_builder",
    "create_wiki_prompt_section_preparer",
    "format_prompt_claim",
    "rank_prompt_claim_freshness",
    "rank_prompt_digest_page",
    "reset_memory_wiki_prompt_section_state_for_tests",
    "sort_prompt_claims",
    # Corpus supplement (Phase 4.3f-mr5).
    "MemoryWikiConfigResolver",
    "WikiCorpusSupplement",
    "WikiCorpusSupplementGetInput",
    "WikiCorpusSupplementSearchInput",
    "create_wiki_corpus_supplement",
    "reset_memory_wiki_corpus_supplement_state_for_tests",
    # Claim health (Phase 4.3d-mr2).
    "WIKI_AGING_DAYS",
    "WIKI_STALE_DAYS",
    "WikiClaimHealth",
    "WikiClaimContradictionCluster",
    "WikiPageContradictionCluster",
    "WikiPageContradictionEntry",
    "WikiFreshness",
    "normalize_claim_status",
    "is_claim_contested_status",
    "assess_page_freshness",
    "assess_claim_freshness",
    "collect_wiki_claim_health",
    "build_claim_contradiction_clusters",
    "build_page_contradiction_clusters",
    # Wiki page summary (Phase 4.3d-mr3).
    "WikiPageSummary",
    "scan_wiki_page_summary",
    "scan_wiki_page_summary_from_file",
    # Compile pipeline (Phase 4.3d-mr4).
    "CompileWikiVaultResult",
    "compile_wiki_vault",
    "should_skip_page_for_compile",
    # Compile render (Phase 4.3d-mr5).
    "DashboardBuild",
    "DASHBOARD_BUILDERS",
    "format_wiki_link",
    "build_open_questions_body",
    "build_contradictions_body",
    "build_low_confidence_body",
    "build_claim_health_body",
    "build_stale_pages_body",
    "render_wiki_dashboards",
    # Compile pages (Phase 4.3d-mr6).
    "PageWriteResult",
    "MAX_RELATED_PAGES_PER_SECTION",
    "MAX_RELATED_LINE_LENGTH",
    "HUMAN_START_MARKER",
    "HUMAN_END_MARKER",
    "build_related_block",
    "build_page_body",
    "write_compiled_pages",
    # Source sync state (Phase 4.3e-mr1).
    "MEMORY_WIKI_SOURCE_SYNC_STATE_NAMESPACE",
    "MEMORY_WIKI_SOURCE_SYNC_STATE_MAX_ENTRIES",
    "MemoryWikiImportedSourceState",
    "MemoryWikiImportedSourceStateEntry",
    "MemoryWikiSourceSyncCapacityError",
    "MemoryWikiSourceSyncStateStore",
    "MemoryWikiSourceSyncStateWritePlan",
    "assert_memory_wiki_source_sync_state_capacity",
    "configure_memory_wiki_source_sync_state_store",
    "create_memory_fallback_state_store",
    "create_memory_wiki_source_sync_state_store",
    "prune_imported_source_entries",
    "read_legacy_memory_wiki_source_sync_state",
    "read_memory_wiki_source_sync_state",
    "resolve_memory_wiki_source_sync_state_path",
    "reset_memory_wiki_source_sync_state_for_tests",
    "set_imported_source_entry",
    "should_skip_imported_source_write",
    "write_memory_wiki_source_sync_state",
    # Import runs state (Phase 4.3e-mr2).
    "LEGACY_IMPORT_RUN_READ_CONCURRENCY",
    "MEMORY_WIKI_IMPORT_RUN_STATE_NAMESPACE",
    "MEMORY_WIKI_IMPORT_RUN_STATE_MAX_ENTRIES",
    "SUPPORTED_IMPORT_TYPES",
    "ChatGptImportRunEntry",
    "ChatGptImportRunRecord",
    "MemoryWikiImportRunMetaStateRecord",
    "MemoryWikiImportRunPathStateRecord",
    "MemoryWikiImportRunStateStore",
    "configure_memory_wiki_import_run_state_store",
    "count_memory_wiki_import_run_state_rows",
    "create_memory_fallback_import_run_store",
    "create_memory_wiki_import_run_state_store",
    "list_memory_wiki_import_run_records",
    "read_legacy_memory_wiki_import_run_records",
    "read_memory_wiki_import_run_record",
    "reset_memory_wiki_import_run_state_for_tests",
    "resolve_memory_wiki_import_runs_dir",
    "write_memory_wiki_import_run_record",
    # Compiled cache (Phase 4.3e-mr3).
    "ActiveVault",
    "COMPILED_CACHE_MAX_BYTES",
    "COMPILED_CACHE_MAX_BYTES_PER_ENTRY",
    "COMPILED_CACHE_MAX_ENTRIES",
    "COMPILED_CACHE_NAMESPACE",
    "COMPILED_CACHE_VERSION",
    "CompiledCacheBlobStore",
    "CompiledCacheEntry",
    "CompiledCacheMetadata",
    "LEGACY_MEMORY_WIKI_COMPILED_CACHE_PATHS",
    "MemoryWikiCompiledCacheSnapshot",
    "MemoryWikiCompiledCacheStore",
    "MemoryWikiCompiledClaim",
    "MemoryWikiCompiledDigestClaim",
    "MemoryWikiCompiledDigestPage",
    "activate_memory_wiki_compiled_cache_owner",
    "configure_memory_wiki_compiled_cache_store",
    "create_memory_wiki_compiled_cache_publication_id",
    "create_memory_wiki_compiled_cache_store",
    "deactivate_memory_wiki_compiled_cache_owners_except",
    "invalidate_memory_wiki_compiled_cache",
    "load_memory_wiki_compiled_cache",
    "reconcile_memory_wiki_compiled_cache_owner",
    "reset_memory_wiki_compiled_cache_for_tests",
    "resolve_memory_wiki_compiled_cache_generation",
    "resolve_memory_wiki_compiled_cache_owner_id",
    "write_memory_wiki_compiled_cache",
    # Apply (Phase 4.3f-mr2).
    "GENERATED_END_MARKER",
    "GENERATED_START_MARKER",
    "HUMAN_END_MARKER",
    "HUMAN_START_MARKER",
    "ApplyMutation",
    "ApplyMutationResult",
    "CreateSynthesisMutation",
    "UpdateMetadataMutation",
    "apply_memory_wiki_mutation",
    "normalize_memory_wiki_mutation_input",
    "reset_memory_wiki_apply_state_for_tests",
    # Bridge (Phase 4.3f-mr2).
    "BRIDGE_IMPORT_KINDS",
    "BridgeArtifact",
    "BridgeArtifactType",
    "BridgeMemoryWikiResult",
    "build_bridge_page_body",
    "collect_bridge_artifacts",
    "filter_memory_wiki_bridge_artifacts",
    "is_path_inside_or_equal",
    "resolve_bridge_page_path",
    "resolve_bridge_render_fingerprint",
    "resolve_bridge_title",
    "resolve_memory_wiki_vault_agent_id",
    "should_import_bridge_artifact",
    "reset_memory_wiki_bridge_state_for_tests",
    # Query (Phase 4.3f-mr1).
    "QUERY_DIRS",
    "QUERY_PAGE_READ_CONCURRENCY",
    "QueryableWikiPage",
    "WIKI_SEARCH_MODES",
    "WikiGetResult",
    "build_lookup_candidates",
    "get_memory_wiki_page",
    "list_wiki_markdown_files",
    "read_queryable_wiki_pages",
    "read_queryable_wiki_pages_by_paths",
    "resolve_queryable_wiki_page_by_lookup",
    "should_search_wiki",
    # Obsidian (Phase 4.3g-mr1).
    "OBSIDIAN_CLI_TIMEOUT_MS",
    "ObsidianCliDeps",
    "ObsidianCliProbe",
    "ObsidianCliResult",
    "probe_obsidian_cli",
    "reset_memory_wiki_obsidian_state_for_tests",
    "run_obsidian_cli",
    "run_obsidian_command",
    "run_obsidian_daily",
    "run_obsidian_open",
    "run_obsidian_search",
    # Status (Phase 4.3g-mr1 — deep).
    "WIKI_STATUS_WARNING_CODES",
    "MemoryWikiDoctorFix",
    "MemoryWikiDoctorReport",
    "MemoryWikiStatus",
    "MemoryWikiStatusObsidianCli",
    "MemoryWikiStatusSourceCounts",
    "MemoryWikiStatusUnsafeLocal",
    "MemoryWikiStatusWarning",
    "build_memory_wiki_doctor_report",
    "build_warnings",
    "render_memory_wiki_doctor",
    "render_memory_wiki_status",
    "resolve_memory_wiki_status",
    # Lint (Phase 4.3g-mr1 — deep).
    "LINT_ISSUE_CATEGORIES",
    "LINT_ISSUE_CODES",
    "WikiLintIssue",
    "WikiLintResult",
    "lint_memory_wiki_vault",
    # Ingest (Phase 4.3g-mr2).
    "IngestMemoryWikiSourceResult",
    "ingest_memory_wiki_source",
    "reset_memory_wiki_ingest_state_for_tests",
    # Source sync orchestrator (Phase 4.3g-mr2).
    "MemoryWikiImportedSourceSyncResult",
    "sync_memory_wiki_imported_sources",
    "reset_memory_wiki_source_sync_state_for_tests",
    # Source page shared (Phase 4.3g-mr2).
    "WriteImportedSourcePageResult",
    "write_imported_source_page",
    # Import runs (Phase 4.3g-mr3).
    "MemoryWikiImportRunSummary",
    "MemoryWikiImportRunsStatus",
    "list_memory_wiki_import_runs",
    "normalize_import_run_summary",
    # Import insights (Phase 4.3g-mr3).
    "MemoryWikiImportInsightCluster",
    "MemoryWikiImportInsightItem",
    "MemoryWikiImportInsightsStatus",
    "list_memory_wiki_import_insights",
    # ChatGPT import (Phase 4.3g-mr3).
    "ChatGptImportResult",
    "import_chatgpt_export",
    # OKF import (Phase 4.3g-mr5).
    "ImportMemoryWikiOkfResult",
    "ImportMemoryWikiOkfWarning",
    "OKF_RESERVED_FILENAMES",
    "OkfBundleMetadata",
    "OkfConceptDocument",
    "format_okf_import_summary",
    "import_memory_wiki_okf_bundle",
    # Setup API (Phase 4.3g-mr6).
    "register_memory_wiki_setup",
    # Wiki CLI (Phase 4.3g-mr7).
    "MemoryWikiCliRegistration",
    "WikiCommandContext",
    "register_wiki_cli",
    # Doctor contract (Phase 4.3g-mr7).
    "STATE_MIGRATIONS",
    "register_memory_wiki_doctor_contracts",
    # Unsafe local import (Phase 4.3g-mr4).
    "DIRECTORY_TEXT_EXTENSIONS",
    "UNSAFE_LOCAL_SYNC_CONCURRENCY",
    "UnsafeLocalArtifact",
    "UnsafeLocalArtifactCollection",
    "collect_unsafe_local_artifacts",
    "detect_fence_language",
    "sync_unsafe_local_sources",
    # Memory palace (Phase 4.3f-mr7).
    "PALACE_ITEM_TOP_CLAIMS",
    "PALACE_ITEM_TOP_CONTRADICTIONS",
    "PALACE_ITEM_TOP_QUESTIONS",
    "PALACE_KIND_LABELS",
    "PALACE_KIND_ORDER",
    "PRIMARY_PALACE_KINDS",
    "MemoryWikiPalaceCluster",
    "MemoryWikiPalaceItem",
    "MemoryWikiPalacePageCounts",
    "MemoryWikiPalaceStatus",
    "compare_palace_items",
    "create_empty_palace_page_counts",
    "extract_snippet",
    "list_memory_wiki_palace",
    "normalize_timestamp",
]


def resolve_artifact_key(absolute_path: str) -> str:
    """Re-export of :func:`.source_path_shared.resolve_artifact_key`."""
    return _source_path_shared.resolve_artifact_key(absolute_path)


def resolve_memory_wiki_timestamp(now_ms: int | float | None = None) -> str:
    """Re-export of :func:`.time.resolve_memory_wiki_timestamp`."""
    return _time.resolve_memory_wiki_timestamp(now_ms)


def append_memory_wiki_log(vault_root: str, entry: dict[str, Any]) -> None:
    """Re-export of :func:`.log.append_memory_wiki_log`."""
    return _log.append_memory_wiki_log(vault_root, entry)


def ensure_memory_wiki_vault_generation(vault_root: str) -> str:
    """Re-export of :func:`.log.ensure_memory_wiki_vault_generation`."""
    return _log.ensure_memory_wiki_vault_generation(vault_root)


def load_memory_wiki_vault_identity(vault_root: str):
    """Re-export of :func:`.log.load_memory_wiki_vault_identity`."""
    return _log.load_memory_wiki_vault_identity(vault_root)


def load_memory_wiki_validated_vault_identity(vault_root: str):
    """Re-export of :func:`.log.load_memory_wiki_validated_vault_identity`."""
    return _log.load_memory_wiki_validated_vault_identity(vault_root)


def resolve_memory_wiki_vault_source_generation(vault_root: str) -> str:
    """Re-export of :func:`.log.resolve_memory_wiki_vault_source_generation`."""
    return _log.resolve_memory_wiki_vault_source_generation(vault_root)


async def write_guarded_vault_page(**kwargs: Any) -> None:
    """Re-export of :func:`.vault_page_write.write_guarded_vault_page`."""
    await _vault_page_write.write_guarded_vault_page(**kwargs)


# Config re-exports so callers can do
# ``from extensions.memory_wiki import memory_wiki_config_schema``.
memory_wiki_config_schema = _config.memory_wiki_config_schema


def resolve_memory_wiki_config(config: Any, **kwargs: Any):
    """Re-export of :func:`.config.resolve_memory_wiki_config`."""
    return _config.resolve_memory_wiki_config(config, **kwargs)


def resolve_memory_wiki_agent_config(**kwargs: Any):
    """Re-export of :func:`.config.resolve_memory_wiki_agent_config`."""
    return _config.resolve_memory_wiki_agent_config(**kwargs)


def resolve_memory_wiki_configured_agent_ids(app_config: Any) -> list[str]:
    """Re-export of :func:`.config.resolve_memory_wiki_configured_agent_ids`."""
    return _config.resolve_memory_wiki_configured_agent_ids(app_config)


def normalize_compatibility_config(*, cfg: dict[str, Any]) -> dict[str, Any]:
    """Re-export of :func:`.config_compat.normalize_compatibility_config`."""
    return _config_compat.normalize_compatibility_config(cfg=cfg)


# Vault init (Phase 4.3c).
WIKI_VAULT_DIRECTORIES = _vault.WIKI_VAULT_DIRECTORIES
WIKI_VAULT_SCAFFOLD = _vault.WIKI_VAULT_SCAFFOLD
InitializeMemoryWikiVaultResult = _vault.InitializeMemoryWikiVaultResult


def initialize_memory_wiki_vault(config: Any, **kwargs: Any):
    """Re-export of :func:`.vault.initialize_memory_wiki_vault`."""
    return _vault.initialize_memory_wiki_vault(config, **kwargs)


# Markdown foundation (Phase 4.3c).
WIKI_PAGE_KINDS = _markdown.WIKI_PAGE_KINDS
WIKI_RAW_SOURCE_MARKER = _markdown.WIKI_RAW_SOURCE_MARKER
WIKI_RELATED_START_MARKER = _markdown.WIKI_RELATED_START_MARKER
WIKI_RELATED_END_MARKER = _markdown.WIKI_RELATED_END_MARKER
parse_wiki_frontmatter = _markdown.parse_wiki_frontmatter
replace_managed_markdown_block = _markdown.replace_managed_markdown_block
with_trailing_newline = _markdown.with_trailing_newline

# Markdown pages (Phase 4.3c-mr2).
WikiClaim = _markdown_pages.WikiClaim
WikiClaimEvidence = _markdown_pages.WikiClaimEvidence
WikiPersonCard = _markdown_pages.WikiPersonCard
WikiRelationship = _markdown_pages.WikiRelationship
WikiPageFrontmatterError = _markdown_pages.WikiPageFrontmatterError
normalize_wiki_claims = _markdown_pages.normalize_wiki_claims
normalize_wiki_person_card = _markdown_pages.normalize_wiki_person_card
normalize_wiki_relationships = _markdown_pages.normalize_wiki_relationships
normalize_source_ids = _markdown_pages.normalize_source_ids
slugify_wiki_segment = _markdown_pages.slugify_wiki_segment
slugify_wiki_page_stem = _markdown_pages.slugify_wiki_page_stem
create_wiki_page_filename = _markdown_pages.create_wiki_page_filename
render_wiki_markdown = _markdown_pages.render_wiki_markdown
extract_title_from_markdown = _markdown_pages.extract_title_from_markdown
extract_wiki_links = _markdown_pages.extract_wiki_links

# Mutation coordinator (Phase 4.3d).
with_memory_wiki_vault_mutation = _mutation_coordinator.with_memory_wiki_vault_mutation
resolve_memory_wiki_vault_mutation_key = (
    _mutation_coordinator.resolve_memory_wiki_vault_mutation_key
)

# Claim health (Phase 4.3d-mr2).
WIKI_AGING_DAYS = _claim_health.WIKI_AGING_DAYS
WIKI_STALE_DAYS = _claim_health.WIKI_STALE_DAYS
WikiClaimHealth = _claim_health.WikiClaimHealth
WikiClaimContradictionCluster = _claim_health.WikiClaimContradictionCluster
WikiPageContradictionCluster = _claim_health.WikiPageContradictionCluster
WikiPageContradictionEntry = _claim_health.WikiPageContradictionEntry
WikiFreshness = _claim_health.WikiFreshness
normalize_claim_status = _claim_health.normalize_claim_status
is_claim_contested_status = _claim_health.is_claim_contested_status
assess_page_freshness = _claim_health.assess_page_freshness
assess_claim_freshness = _claim_health.assess_claim_freshness
collect_wiki_claim_health = _claim_health.collect_wiki_claim_health
build_claim_contradiction_clusters = _claim_health.build_claim_contradiction_clusters
build_page_contradiction_clusters = _claim_health.build_page_contradiction_clusters

# Wiki page summary (Phase 4.3d-mr3).
WikiPageSummary = _wiki_page_summary.WikiPageSummary
scan_wiki_page_summary = _wiki_page_summary.scan_wiki_page_summary
scan_wiki_page_summary_from_file = _wiki_page_summary.scan_wiki_page_summary_from_file

# Compile pipeline (Phase 4.3d-mr4).
CompileWikiVaultResult = _compile_pipeline.CompileWikiVaultResult
compile_wiki_vault = _compile_pipeline.compile_wiki_vault
should_skip_page_for_compile = _compile_pipeline.should_skip_page_for_compile

# Compile render (Phase 4.3d-mr5).
DashboardBuild = _compile_render.DashboardBuild
DASHBOARD_BUILDERS = _compile_render.DASHBOARD_BUILDERS
format_wiki_link = _compile_render.format_wiki_link
build_open_questions_body = _compile_render.build_open_questions_body
build_contradictions_body = _compile_render.build_contradictions_body
build_low_confidence_body = _compile_render.build_low_confidence_body
build_claim_health_body = _compile_render.build_claim_health_body
build_stale_pages_body = _compile_render.build_stale_pages_body
render_wiki_dashboards = _compile_render.render_wiki_dashboards

# Compile pages (Phase 4.3d-mr6).
PageWriteResult = _compile_pages.PageWriteResult
MAX_RELATED_PAGES_PER_SECTION = _compile_pages.MAX_RELATED_PAGES_PER_SECTION
MAX_RELATED_LINE_LENGTH = _compile_pages.MAX_RELATED_LINE_LENGTH
HUMAN_START_MARKER = _compile_pages.HUMAN_START_MARKER
HUMAN_END_MARKER = _compile_pages.HUMAN_END_MARKER
build_related_block = _compile_pages.build_related_block
build_page_body = _compile_pages.build_page_body
write_compiled_pages = _compile_pages.write_compiled_pages

# Source sync state (Phase 4.3e-mr1).
MEMORY_WIKI_SOURCE_SYNC_STATE_NAMESPACE = _source_sync_state.MEMORY_WIKI_SOURCE_SYNC_STATE_NAMESPACE
MEMORY_WIKI_SOURCE_SYNC_STATE_MAX_ENTRIES = (
    _source_sync_state.MEMORY_WIKI_SOURCE_SYNC_STATE_MAX_ENTRIES
)
MemoryWikiImportedSourceState = _source_sync_state.MemoryWikiImportedSourceState
MemoryWikiImportedSourceStateEntry = _source_sync_state.MemoryWikiImportedSourceStateEntry
MemoryWikiSourceSyncCapacityError = _source_sync_state.MemoryWikiSourceSyncCapacityError
MemoryWikiSourceSyncStateStore = _source_sync_state.MemoryWikiSourceSyncStateStore
MemoryWikiSourceSyncStateWritePlan = _source_sync_state.MemoryWikiSourceSyncStateWritePlan
assert_memory_wiki_source_sync_state_capacity = (
    _source_sync_state.assert_memory_wiki_source_sync_state_capacity
)
configure_memory_wiki_source_sync_state_store = (
    _source_sync_state.configure_memory_wiki_source_sync_state_store
)
create_memory_fallback_state_store = _source_sync_state.create_memory_fallback_state_store
create_memory_wiki_source_sync_state_store = (
    _source_sync_state.create_memory_wiki_source_sync_state_store
)
prune_imported_source_entries = _source_sync_state.prune_imported_source_entries
read_legacy_memory_wiki_source_sync_state = (
    _source_sync_state.read_legacy_memory_wiki_source_sync_state
)
read_memory_wiki_source_sync_state = _source_sync_state.read_memory_wiki_source_sync_state
resolve_memory_wiki_source_sync_state_path = (
    _source_sync_state.resolve_memory_wiki_source_sync_state_path
)
reset_memory_wiki_source_sync_state_for_tests = (
    _source_sync_state.reset_memory_wiki_source_sync_state_for_tests
)
set_imported_source_entry = _source_sync_state.set_imported_source_entry
should_skip_imported_source_write = _source_sync_state.should_skip_imported_source_write
write_memory_wiki_source_sync_state = _source_sync_state.write_memory_wiki_source_sync_state

# Import runs state (Phase 4.3e-mr2).
LEGACY_IMPORT_RUN_READ_CONCURRENCY = _import_runs_state.LEGACY_IMPORT_RUN_READ_CONCURRENCY
MEMORY_WIKI_IMPORT_RUN_STATE_NAMESPACE = _import_runs_state.MEMORY_WIKI_IMPORT_RUN_STATE_NAMESPACE
MEMORY_WIKI_IMPORT_RUN_STATE_MAX_ENTRIES = (
    _import_runs_state.MEMORY_WIKI_IMPORT_RUN_STATE_MAX_ENTRIES
)
SUPPORTED_IMPORT_TYPES = _import_runs_state.SUPPORTED_IMPORT_TYPES
ChatGptImportRunEntry = _import_runs_state.ChatGptImportRunEntry
ChatGptImportRunRecord = _import_runs_state.ChatGptImportRunRecord
MemoryWikiImportRunMetaStateRecord = _import_runs_state.MemoryWikiImportRunMetaStateRecord
MemoryWikiImportRunPathStateRecord = _import_runs_state.MemoryWikiImportRunPathStateRecord
MemoryWikiImportRunStateStore = _import_runs_state.MemoryWikiImportRunStateStore
configure_memory_wiki_import_run_state_store = (
    _import_runs_state.configure_memory_wiki_import_run_state_store
)
count_memory_wiki_import_run_state_rows = _import_runs_state.count_memory_wiki_import_run_state_rows
create_memory_fallback_import_run_store = _import_runs_state.create_memory_fallback_import_run_store
create_memory_wiki_import_run_state_store = (
    _import_runs_state.create_memory_wiki_import_run_state_store
)
list_memory_wiki_import_run_records = _import_runs_state.list_memory_wiki_import_run_records
read_legacy_memory_wiki_import_run_records = (
    _import_runs_state.read_legacy_memory_wiki_import_run_records
)
read_memory_wiki_import_run_record = _import_runs_state.read_memory_wiki_import_run_record
reset_memory_wiki_import_run_state_for_tests = (
    _import_runs_state.reset_memory_wiki_import_run_state_for_tests
)
resolve_memory_wiki_import_runs_dir = _import_runs_state.resolve_memory_wiki_import_runs_dir
write_memory_wiki_import_run_record = _import_runs_state.write_memory_wiki_import_run_record

# Compiled cache (Phase 4.3e-mr3).
ActiveVault = _compiled_cache.ActiveVault
COMPILED_CACHE_MAX_BYTES = _compiled_cache.COMPILED_CACHE_MAX_BYTES
COMPILED_CACHE_MAX_BYTES_PER_ENTRY = _compiled_cache.COMPILED_CACHE_MAX_BYTES_PER_ENTRY
COMPILED_CACHE_MAX_ENTRIES = _compiled_cache.COMPILED_CACHE_MAX_ENTRIES
COMPILED_CACHE_NAMESPACE = _compiled_cache.COMPILED_CACHE_NAMESPACE
COMPILED_CACHE_VERSION = _compiled_cache.COMPILED_CACHE_VERSION
CompiledCacheBlobStore = _compiled_cache.CompiledCacheBlobStore
CompiledCacheEntry = _compiled_cache.CompiledCacheEntry
CompiledCacheMetadata = _compiled_cache.CompiledCacheMetadata
LEGACY_MEMORY_WIKI_COMPILED_CACHE_PATHS = _compiled_cache.LEGACY_MEMORY_WIKI_COMPILED_CACHE_PATHS
MemoryWikiCompiledCacheSnapshot = _compiled_cache.MemoryWikiCompiledCacheSnapshot
MemoryWikiCompiledCacheStore = _compiled_cache.MemoryWikiCompiledCacheStore
MemoryWikiCompiledClaim = _compiled_cache.MemoryWikiCompiledClaim
MemoryWikiCompiledDigestClaim = _compiled_cache.MemoryWikiCompiledDigestClaim
MemoryWikiCompiledDigestPage = _compiled_cache.MemoryWikiCompiledDigestPage
activate_memory_wiki_compiled_cache_owner = (
    _compiled_cache.activate_memory_wiki_compiled_cache_owner
)
configure_memory_wiki_compiled_cache_store = (
    _compiled_cache.configure_memory_wiki_compiled_cache_store
)
create_memory_wiki_compiled_cache_publication_id = (
    _compiled_cache.create_memory_wiki_compiled_cache_publication_id
)
create_memory_wiki_compiled_cache_store = _compiled_cache.create_memory_wiki_compiled_cache_store
deactivate_memory_wiki_compiled_cache_owners_except = (
    _compiled_cache.deactivate_memory_wiki_compiled_cache_owners_except
)
invalidate_memory_wiki_compiled_cache = _compiled_cache.invalidate_memory_wiki_compiled_cache
load_memory_wiki_compiled_cache = _compiled_cache.load_memory_wiki_compiled_cache
reconcile_memory_wiki_compiled_cache_owner = (
    _compiled_cache.reconcile_memory_wiki_compiled_cache_owner
)
reset_memory_wiki_compiled_cache_for_tests = (
    _compiled_cache.reset_memory_wiki_compiled_cache_for_tests
)
resolve_memory_wiki_compiled_cache_generation = (
    _compiled_cache.resolve_memory_wiki_compiled_cache_generation
)
resolve_memory_wiki_compiled_cache_owner_id = (
    _compiled_cache.resolve_memory_wiki_compiled_cache_owner_id
)
write_memory_wiki_compiled_cache = _compiled_cache.write_memory_wiki_compiled_cache

# Apply (Phase 4.3f-mr2).
GENERATED_END_MARKER = _apply.GENERATED_END_MARKER
GENERATED_START_MARKER = _apply.GENERATED_START_MARKER
HUMAN_END_MARKER = _apply.HUMAN_END_MARKER
HUMAN_START_MARKER = _apply.HUMAN_START_MARKER
ApplyMutation = _apply.ApplyMutation
ApplyMutationResult = _apply.ApplyMutationResult
CreateSynthesisMutation = _apply.CreateSynthesisMutation
UpdateMetadataMutation = _apply.UpdateMetadataMutation
apply_memory_wiki_mutation = _apply.apply_memory_wiki_mutation
normalize_memory_wiki_mutation_input = _apply.normalize_memory_wiki_mutation_input
reset_memory_wiki_apply_state_for_tests = _apply.reset_memory_wiki_apply_state_for_tests

# Bridge (Phase 4.3f-mr2).
BRIDGE_IMPORT_KINDS = _bridge.BRIDGE_IMPORT_KINDS
BridgeArtifact = _bridge.BridgeArtifact
BridgeArtifactType = _bridge.BridgeArtifactType
BridgeMemoryWikiResult = _bridge.BridgeMemoryWikiResult
build_bridge_page_body = _bridge.build_bridge_page_body
collect_bridge_artifacts = _bridge.collect_bridge_artifacts
filter_memory_wiki_bridge_artifacts = _bridge.filter_memory_wiki_bridge_artifacts
is_path_inside_or_equal = _bridge.is_path_inside_or_equal
resolve_bridge_page_path = _bridge.resolve_bridge_page_path
resolve_bridge_render_fingerprint = _bridge.resolve_bridge_render_fingerprint
resolve_bridge_title = _bridge.resolve_bridge_title
resolve_memory_wiki_vault_agent_id = _bridge.resolve_memory_wiki_vault_agent_id
should_import_bridge_artifact = _bridge.should_import_bridge_artifact
reset_memory_wiki_bridge_state_for_tests = _bridge.reset_memory_wiki_bridge_state_for_tests

# Query (Phase 4.3f-mr1).
QUERY_DIRS = _query.QUERY_DIRS
QUERY_PAGE_READ_CONCURRENCY = _query.QUERY_PAGE_READ_CONCURRENCY
QueryableWikiPage = _query.QueryableWikiPage
WIKI_SEARCH_MODES = _query.WIKI_SEARCH_MODES
WikiGetResult = _query.WikiGetResult
build_lookup_candidates = _query.build_lookup_candidates
get_memory_wiki_page = _query.get_memory_wiki_page
list_wiki_markdown_files = _query.list_wiki_markdown_files
read_queryable_wiki_pages = _query.read_queryable_wiki_pages
read_queryable_wiki_pages_by_paths = _query.read_queryable_wiki_pages_by_paths
resolve_queryable_wiki_page_by_lookup = _query.resolve_queryable_wiki_page_by_lookup
should_search_wiki = _query.should_search_wiki

# Prompt section (Phase 4.3f-mr6).
DIGEST_MAX_CLAIMS_PER_PAGE = _prompt_section.DIGEST_MAX_CLAIMS_PER_PAGE
DIGEST_MAX_PAGES = _prompt_section.DIGEST_MAX_PAGES
MemoryPromptSectionBuilder = _prompt_section.MemoryPromptSectionBuilder
MemoryPromptSectionParams = _prompt_section.MemoryPromptSectionParams
MemoryPromptSectionPreparer = _prompt_section.MemoryPromptSectionPreparer
build_digest_prompt_section = _prompt_section.build_digest_prompt_section
build_wiki_tool_guidance = _prompt_section.build_wiki_tool_guidance
create_wiki_prompt_section_builder = _prompt_section.create_wiki_prompt_section_builder
create_wiki_prompt_section_preparer = _prompt_section.create_wiki_prompt_section_preparer
format_prompt_claim = _prompt_section.format_prompt_claim
rank_prompt_claim_freshness = _prompt_section.rank_prompt_claim_freshness
rank_prompt_digest_page = _prompt_section.rank_prompt_digest_page
reset_memory_wiki_prompt_section_state_for_tests = (
    _prompt_section.reset_memory_wiki_prompt_section_state_for_tests
)
sort_prompt_claims = _prompt_section.sort_prompt_claims

# Corpus supplement (Phase 4.3f-mr5).
MemoryWikiConfigResolver = _corpus_supplement.MemoryWikiConfigResolver
WikiCorpusSupplement = _corpus_supplement.WikiCorpusSupplement
WikiCorpusSupplementGetInput = _corpus_supplement.WikiCorpusSupplementGetInput
WikiCorpusSupplementSearchInput = _corpus_supplement.WikiCorpusSupplementSearchInput
create_wiki_corpus_supplement = _corpus_supplement.create_wiki_corpus_supplement
reset_memory_wiki_corpus_supplement_state_for_tests = (
    _corpus_supplement.reset_memory_wiki_corpus_supplement_state_for_tests
)

# Memory palace (Phase 4.3f-mr7).
PALACE_ITEM_TOP_CLAIMS = _memory_palace.PALACE_ITEM_TOP_CLAIMS
PALACE_ITEM_TOP_CONTRADICTIONS = _memory_palace.PALACE_ITEM_TOP_CONTRADICTIONS
PALACE_ITEM_TOP_QUESTIONS = _memory_palace.PALACE_ITEM_TOP_QUESTIONS
PALACE_KIND_LABELS = _memory_palace.PALACE_KIND_LABELS
PALACE_KIND_ORDER = _memory_palace.PALACE_KIND_ORDER
PRIMARY_PALACE_KINDS = _memory_palace.PRIMARY_PALACE_KINDS
MemoryWikiPalaceCluster = _memory_palace.MemoryWikiPalaceCluster
MemoryWikiPalaceItem = _memory_palace.MemoryWikiPalaceItem
MemoryWikiPalacePageCounts = _memory_palace.MemoryWikiPalacePageCounts
MemoryWikiPalaceStatus = _memory_palace.MemoryWikiPalaceStatus
compare_palace_items = _memory_palace.compare_palace_items
create_empty_palace_page_counts = _memory_palace.create_empty_palace_page_counts
extract_snippet = _memory_palace.extract_snippet
list_memory_wiki_palace = _memory_palace.list_memory_wiki_palace
normalize_timestamp = _memory_palace.normalize_timestamp

# Obsidian (Phase 4.3g-mr1).
OBSIDIAN_CLI_TIMEOUT_MS = _obsidian.OBSIDIAN_CLI_TIMEOUT_MS
ObsidianCliDeps = _obsidian.ObsidianCliDeps
ObsidianCliProbe = _obsidian.ObsidianCliProbe
ObsidianCliResult = _obsidian.ObsidianCliResult
probe_obsidian_cli = _obsidian.probe_obsidian_cli
reset_memory_wiki_obsidian_state_for_tests = _obsidian.reset_memory_wiki_obsidian_state_for_tests
run_obsidian_cli = _obsidian.run_obsidian_cli
run_obsidian_command = _obsidian.run_obsidian_command
run_obsidian_daily = _obsidian.run_obsidian_daily
run_obsidian_open = _obsidian.run_obsidian_open
run_obsidian_search = _obsidian.run_obsidian_search

# Status (Phase 4.3g-mr1 — deep). Replaces the
# Phase 4.3f-mr3 stub.
WIKI_STATUS_WARNING_CODES = _status.WIKI_STATUS_WARNING_CODES
MemoryWikiDoctorFix = _status.MemoryWikiDoctorFix
MemoryWikiDoctorReport = _status.MemoryWikiDoctorReport
MemoryWikiStatus = _status.MemoryWikiStatus
MemoryWikiStatusObsidianCli = _status.MemoryWikiStatusObsidianCli
MemoryWikiStatusSourceCounts = _status.MemoryWikiStatusSourceCounts
MemoryWikiStatusUnsafeLocal = _status.MemoryWikiStatusUnsafeLocal
MemoryWikiStatusWarning = _status.MemoryWikiStatusWarning
build_memory_wiki_doctor_report = _status.build_memory_wiki_doctor_report
build_warnings = _status.build_warnings
render_memory_wiki_doctor = _status.render_memory_wiki_doctor
render_memory_wiki_status = _status.render_memory_wiki_status
resolve_memory_wiki_status = _status.resolve_memory_wiki_status

# Lint (Phase 4.3g-mr1 — deep). Replaces the
# Phase 4.3f-mr3 stub.
LINT_ISSUE_CATEGORIES = _lint.LINT_ISSUE_CATEGORIES
LINT_ISSUE_CODES = _lint.LINT_ISSUE_CODES
WikiLintIssue = _lint.WikiLintIssue
WikiLintResult = _lint.WikiLintResult
lint_memory_wiki_vault = _lint.lint_memory_wiki_vault

# Ingest (Phase 4.3g-mr2).
IngestMemoryWikiSourceResult = _ingest.IngestMemoryWikiSourceResult
ingest_memory_wiki_source = _ingest.ingest_memory_wiki_source
reset_memory_wiki_ingest_state_for_tests = _ingest.reset_memory_wiki_ingest_state_for_tests

# Source sync orchestrator (Phase 4.3g-mr2).
MemoryWikiImportedSourceSyncResult = _source_sync.MemoryWikiImportedSourceSyncResult
sync_memory_wiki_imported_sources = _source_sync.sync_memory_wiki_imported_sources
reset_memory_wiki_source_sync_state_for_tests = (
    _source_sync.reset_memory_wiki_source_sync_state_for_tests
)

# Source page shared (Phase 4.3g-mr2).
WriteImportedSourcePageResult = _source_page_shared.WriteImportedSourcePageResult
write_imported_source_page = _source_page_shared.write_imported_source_page

# Import runs (Phase 4.3g-mr3).
MemoryWikiImportRunSummary = _import_runs.MemoryWikiImportRunSummary
MemoryWikiImportRunsStatus = _import_runs.MemoryWikiImportRunsStatus
list_memory_wiki_import_runs = _import_runs.list_memory_wiki_import_runs
normalize_import_run_summary = _import_runs.normalize_import_run_summary

# Import insights (Phase 4.3g-mr3).
MemoryWikiImportInsightCluster = _import_insights.MemoryWikiImportInsightCluster
MemoryWikiImportInsightItem = _import_insights.MemoryWikiImportInsightItem
MemoryWikiImportInsightsStatus = _import_insights.MemoryWikiImportInsightsStatus
list_memory_wiki_import_insights = _import_insights.list_memory_wiki_import_insights

# ChatGPT import (Phase 4.3g-mr3).
ChatGptImportResult = _chatgpt_import.ChatGptImportResult
import_chatgpt_export = _chatgpt_import.import_chatgpt_export

# OKF import (Phase 4.3g-mr5).
ImportMemoryWikiOkfResult = _okf.ImportMemoryWikiOkfResult
ImportMemoryWikiOkfWarning = _okf.ImportMemoryWikiOkfWarning
OKF_RESERVED_FILENAMES = _okf.OKF_RESERVED_FILENAMES
OkfBundleMetadata = _okf.OkfBundleMetadata
OkfConceptDocument = _okf.OkfConceptDocument
format_okf_import_summary = _okf.format_okf_import_summary
import_memory_wiki_okf_bundle = _okf.import_memory_wiki_okf_bundle

# Setup API (Phase 4.3g-mr6).
register_memory_wiki_setup = _setup_api.register_memory_wiki_setup

# Wiki CLI (Phase 4.3g-mr7).
MemoryWikiCliRegistration = _wiki_cli.MemoryWikiCliRegistration
WikiCommandContext = _wiki_cli.WikiCommandContext
register_wiki_cli = _wiki_cli.register_wiki_cli

# Doctor contract (Phase 4.3g-mr7).
STATE_MIGRATIONS = _doctor_contract.STATE_MIGRATIONS
register_memory_wiki_doctor_contracts = _doctor_contract.register_memory_wiki_doctor_contracts

# Unsafe local import (Phase 4.3g-mr4).
DIRECTORY_TEXT_EXTENSIONS = _unsafe_local.DIRECTORY_TEXT_EXTENSIONS
UNSAFE_LOCAL_SYNC_CONCURRENCY = _unsafe_local.UNSAFE_LOCAL_SYNC_CONCURRENCY
UnsafeLocalArtifact = _unsafe_local.UnsafeLocalArtifact
UnsafeLocalArtifactCollection = _unsafe_local.UnsafeLocalArtifactCollection
collect_unsafe_local_artifacts = _unsafe_local.collect_unsafe_local_artifacts
detect_fence_language = _unsafe_local.detect_fence_language
sync_unsafe_local_sources = _unsafe_local.sync_unsafe_local_sources
