"""jarvis.shared — shared utility modules.

OpenClaw parity: mirrors ``openclaw-main/src/shared/`` directory.
"""
from __future__ import annotations

from .avatar_policy import (  # noqa: F401
    AVATAR_MAX_BYTES,
    has_avatar_uri_scheme,
    is_avatar_data_url,
    is_avatar_http_url,
    is_path_within_root,
    is_supported_local_avatar_extension,
    is_windows_absolute_path,
    looks_like_avatar_path,
    resolve_avatar_mime,
)
from .balanced_json import (  # noqa: F401
    BalancedJsonFragment,
    extract_balanced_json_fragments,
    extract_balanced_json_prefix,
)
from .entry_status import (  # noqa: F401
    evaluate_entry_metadata_requirements,
    evaluate_entry_requirements_for_current_platform,
)
from .fast_mode import (  # noqa: F401
    DEFAULT_FAST_MODE_AUTO_ON_SECONDS,
    FastMode,
    FastModeAutoProgressState,
    FastModeSource,
    format_fast_mode_auto_label,
    format_fast_mode_auto_progress_text,
    format_fast_mode_command_options,
    format_fast_mode_current_status,
    format_fast_mode_source_suffix,
    format_fast_mode_status_value,
    format_fast_mode_value,
    resolve_fast_mode_for_elapsed,
    resolve_fast_mode_model_auto_on_seconds,
    resolve_fast_mode_model_params,
)
from .frontmatter import (  # noqa: F401
    LEGACY_MANIFEST_KEYS,
    MANIFEST_KEY,
    apply_openclaw_manifest_install_common_fields,
    get_frontmatter_string,
    normalize_string_list,
    parse_frontmatter_bool,
    parse_openclaw_manifest_install_base,
    resolve_openclaw_manifest_block,
    resolve_openclaw_manifest_install,
    resolve_openclaw_manifest_os,
    resolve_openclaw_manifest_requires,
)
from .lazy_promise import (  # noqa: F401
    LazyPromiseLoader,
    create_lazy_import_loader,
    create_lazy_promise,
    create_lazy_promise_loader,
    get_or_create_promise,
)
from .operator_scope_compat import (  # noqa: F401
    OPERATOR_ADMIN_SCOPE,
    OPERATOR_READ_SCOPE,
    OPERATOR_ROLE,
    OPERATOR_SCOPE_PREFIX,
    OPERATOR_WRITE_SCOPE,
    resolve_missing_requested_scope,
    resolve_scope_outside_requested_roles,
    role_scopes_allow,
)
from .pid_alive import (  # noqa: F401
    get_file_lock_process_start_time,
    get_process_start_time,
    is_pid_alive,
    is_pid_definitely_dead,
)
from .scoped_expiring_id_cache import (  # noqa: F401
    ScopedExpiringIdCache,
    create_scoped_expiring_id_cache,
)
from .thread_binding_lifecycle import (  # noqa: F401
    ThreadBindingLifecycleRecord,
    resolve_thread_binding_lifecycle,
)
