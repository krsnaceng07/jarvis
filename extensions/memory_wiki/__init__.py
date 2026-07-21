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
    claim_health as _claim_health,
    compile_pages as _compile_pages,
    compile_pipeline as _compile_pipeline,
    compile_render as _compile_render,
    compiled_cache as _compiled_cache,
    config as _config,
    config_compat as _config_compat,
    corpus_supplement as _corpus_supplement,
    import_runs_state as _import_runs_state,
    log as _log,
    markdown as _markdown,
    markdown_pages as _markdown_pages,
    mutation_coordinator as _mutation_coordinator,
    prompt_section as _prompt_section,
    query as _query,
    source_path_shared as _source_path_shared,
    source_sync_state as _source_sync_state,
    time as _time,
    vault as _vault,
    vault_page_write as _vault_page_write,
    wiki_page_summary as _wiki_page_summary,
)

_LOGGER = logging.getLogger("jarvis.extensions.memory_wiki")


def register_memory_wiki(api: PluginApi) -> None:
    """Register the memory-wiki plugin with the host.

    Phase 4.3a ships a minimal registration: log a
    startup line so operators can see the plugin
    loaded, and surface the foundation helpers
    through ``api.runtime`` (so other sub-phases
    can call them without an import cycle). The
    full registration (gateway methods, tool
    registrations, prompt section, lifecycle
    service) is wired in Phase 4.3g.
    """
    logger = getattr(api, "logger", None)
    log_fn = getattr(logger, "info", None) if logger is not None else None
    if callable(log_fn):
        log_fn("memory-wiki: phase 4.3a foundation loaded")
    # Phase 4.3a does not register any service or
    # tool yet. Subsequent sub-phases will add:
    #   - register_service for the compiled-cache
    #     lifecycle (Phase 4.3e)
    #   - register_tool for the 5 wiki tools
    #     (Phase 4.3f)
    #   - register_cli for the ``wiki`` command
    #     (Phase 4.3g)


# ``define_plugin_entry`` is the SDK helper that
# builds the ``.entry`` symbol the host looks for
# when it imports the extension. The Phase 4.3a
# entry exposes a minimal registration callback;
# Phase 4.3g will replace it with the full surface.
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
