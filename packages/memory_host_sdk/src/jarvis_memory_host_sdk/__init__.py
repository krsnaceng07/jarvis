"""jarvis_memory_host_sdk — Public memory API for host + plugins.

OpenClaw parity: mirrors
``packages/memory-host-sdk/src/memory-host-sdk/*.ts``
(60+ files: the public surface re-exported from the
``host/*.ts`` and ``memory-host-sdk/*.ts`` modules).

This package re-exports the 34 ``memory_host_*`` modules
that were originally ported into
``packages/plugin_sdk/src/jarvis_sdk/`` (Phases 5.1–5.5).

The re-export shim is temporary: a follow-up phase will
physically move the modules here and update all
``jarvis_sdk.memory_host_*`` import sites to the new
``jarvis_memory_host_sdk.memory_host_*`` location.
"""

from __future__ import annotations

# Phase 5.1 — event store (4 modules).
from jarvis_sdk.memory_host_event_types import (  # noqa: F401
    MemoryHostEvent,
    MemoryHostEventRecord,
    MemoryHostEventStorageMetadata,
    MemoryHostPromotionAppliedEvent,
    MemoryHostPromotionCandidate,
    MemoryHostRecallRecordedEvent,
    MemoryHostRecallResult,
    MemoryHostRecallSkippedEvent,
    MemoryHostDreamCompletedEvent,
)
from jarvis_sdk.memory_host_events import (  # noqa: F401
    append_memory_host_event,
    read_memory_host_event_records,
    read_memory_host_events,
)
from jarvis_sdk.memory_host_event_store import (  # noqa: F401
    normalize_memory_host_event_record_for_storage,
    register_memory_host_event,
    list_stored_memory_host_events,
    set_max_memory_host_events_for_tests,
)
from jarvis_sdk.memory_host_event_export import (  # noqa: F401
    serialize_memory_host_event_export,
)

# Phase 5.2 — hash / status / secret.
from jarvis_sdk.memory_host_hash import hash_text  # noqa: F401
from jarvis_sdk.memory_host_status_format import (  # noqa: F401
    Tone,
    resolve_memory_cache_summary,
    resolve_memory_fts_state,
    resolve_memory_vector_state,
)
from jarvis_sdk.memory_host_secret import (  # noqa: F401
    has_configured_memory_secret_input,
    resolve_memory_secret_input_string,
)
from jarvis_sdk.memory_host_secret_input_utils import (  # noqa: F401
    DEFAULT_SECRET_PROVIDER_ALIAS,
    ENV_SECRET_REF_ID_RE,
    ENV_SECRET_TEMPLATE_RE,
    LEGACY_SECRETREF_ENV_MARKER_PREFIX,
    SECRET_REF_SOURCES,
    SecretRef,
    SecretRefSource,
    coerce_secret_ref,
    has_configured_memory_secret_input_value,
    normalize_env_secret_input_string,
    normalize_resolved_memory_secret_input_string,
    parse_env_template_secret_ref,
    parse_legacy_secret_ref_env_marker,
    resolve_memory_secret_input_ref,
)

# Phase 5.3 — query expansion + multimodal.
from jarvis_sdk.memory_host_query_expansion import (  # noqa: F401
    ExtractKeywordsOptions,
    STOP_WORDS_AR,
    STOP_WORDS_EN,
    STOP_WORDS_ES,
    STOP_WORDS_JA,
    STOP_WORDS_KO,
    STOP_WORDS_PT,
    STOP_WORDS_ZH,
    extract_keywords,
    is_query_stop_word_token,
)
from jarvis_sdk.memory_host_multimodal import (  # noqa: F401
    DEFAULT_MEMORY_MULTIMODAL_MAX_FILE_BYTES,
    MemoryMultimodalModality,
    MemoryMultimodalSelection,
    MemoryMultimodalSettings,
    build_case_insensitive_extension_glob,
    build_memory_multimodal_label,
    classify_memory_multimodal_path,
    get_memory_multimodal_extensions,
    is_memory_multimodal_enabled,
    normalize_memory_multimodal_settings,
)

# Phase 5.4 — internal + read-file.
from jarvis_sdk.memory_host_internal import (  # noqa: F401
    MEMORY_HOST_ROOT_FILENAME,
    MemoryChunk,
    MemoryFileEntry,
    build_file_entry,
    build_multimodal_chunk_for_indexing,
    chunk_markdown,
    cosine_similarity,
    ensure_dir,
    ensure_memory_host_dir,
    is_memory_path,
    list_memory_files,
    normalize_extra_memory_paths,
    parse_embedding,
    remap_chunk_lines,
    run_memory_host_tasks_with_concurrency,
    run_with_concurrency,
)
from jarvis_sdk.memory_host_read_file import (  # noqa: F401
    read_agent_memory_file,
    read_memory_file,
)
from jarvis_sdk.memory_host_read_file_shared import (  # noqa: F401
    DEFAULT_MEMORY_READ_LINES,
    DEFAULT_MEMORY_READ_MAX_CHARS,
    MemoryReadResult,
    build_memory_read_result,
    build_memory_read_result_from_slice,
)
from jarvis_sdk.memory_host_read_retry import (  # noqa: F401
    is_transient_memory_read_error,
    retry_transient_memory_read,
)
from jarvis_sdk.memory_host_fs_utils import (  # noqa: F401
    WalkDirectoryEntry,
    assert_no_symlink_parents,
    is_file_missing_error,
    is_path_inside,
    is_path_inside_with_realpath,
    read_regular_file,
    root,
    stat_regular_file,
    walk_directory,
)
from jarvis_sdk.memory_host_cjk_chars import (  # noqa: F401
    CHARS_PER_TOKEN_ESTIMATE,
    estimate_string_chars,
    estimate_tokens_from_chars,
)
from jarvis_sdk.memory_host_embedding_inputs import (  # noqa: F401
    EmbeddingInput,
    EmbeddingInputInlineDataPart,
    EmbeddingInputPart,
    EmbeddingInputTextPart,
    build_text_embedding_input,
    has_non_text_embedding_parts,
)
from jarvis_sdk.memory_host_embedding_input_limits import (  # noqa: F401
    estimate_structured_embedding_input_bytes,
    estimate_utf8_bytes,
    split_text_to_utf8_byte_limit,
)
from jarvis_sdk.memory_host_runtime_io import detect_mime  # noqa: F401
from jarvis_sdk.memory_host_runtime_memory import (  # noqa: F401
    CANONICAL_ROOT_MEMORY_FILENAME,
    LEGACY_ROOT_MEMORY_FILENAME,
    ROOT_MEMORY_REPAIR_RELATIVE_DIR,
    exact_workspace_entry_exists,
    resolve_canonical_root_memory_file,
    resolve_canonical_root_memory_path,
    resolve_legacy_root_memory_path,
    resolve_root_memory_repair_dir,
    should_skip_root_memory_auxiliary_path,
)
from jarvis_sdk.memory_host_config_utils import (  # noqa: F401
    AgentConfig,
    AgentContextLimitsConfig,
    DEFAULT_AGENT_ID,
    LEGACY_STATE_DIRNAMES,
    MemorySearchConfig,
    NEW_STATE_DIRNAME,
    OpenClawConfig,
    resolve_memory_host_agent_context_limits,
    resolve_memory_host_agent_workspace_dir,
    resolve_memory_host_search_path_config,
)

# Phase 5.5 — error utils.
from jarvis_sdk.memory_host_error_utils import (  # noqa: F401
    format_error_message,
    redact_sensitive_text,
)

# Phase 4 — search facade.
from jarvis_sdk.memory_host_search import close_active_memory_search_manager  # noqa: F401

# Public facades (5 files).
from jarvis_sdk.memory_host_hash_facade import *  # noqa: F401, F403
from jarvis_sdk.memory_host_multimodal_facade import *  # noqa: F401, F403
from jarvis_sdk.memory_host_read_retry_facade import *  # noqa: F401, F403
from jarvis_sdk.memory_host_read_file_facade import *  # noqa: F401, F403
from jarvis_sdk.memory_host_read_file_shared_facade import *  # noqa: F401, F403
from jarvis_sdk.memory_host_error_utils_facade import *  # noqa: F401, F403
from jarvis_sdk.memory_host_internal_facade import *  # noqa: F401, F403
