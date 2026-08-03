"""jarvis.utils — shared utility helpers.

OpenClaw parity: mirrors ``openclaw-main/src/utils/`` directory.
"""
from __future__ import annotations

from .account_id import normalize_account_id  # noqa: F401
from .boolean import (  # noqa: F401
    DEFAULT_FALSY,
    DEFAULT_TRUTHY,
    as_boolean,
    parse_boolean_value,
)
from .chunk_items import chunk_items  # noqa: F401
from .cjk_chars import (  # noqa: F401
    CHARS_PER_TOKEN_ESTIMATE,
    estimate_string_chars,
    estimate_tokens_from_chars,
)
from .conversation_target import (  # noqa: F401
    ConversationTargetParams,
    normalize_conversation_target_params,
)
from .delivery_context import (  # noqa: F401
    DeliveryContext,
    delivery_context_from_session,
    delivery_context_key,
    merge_delivery_context,
    normalize_delivery_context,
)
from .directive_tags import (  # noqa: F401
    DisplayMessageWithContent,
    InlineDirectiveParseResult,
    MAX_REPLY_DIRECTIVE_ID_LENGTH,
    parse_inline_directives,
    sanitize_reply_directive_id,
    strip_inline_directive_tags_for_delivery,
    strip_inline_directive_tags_for_display,
    strip_inline_directive_tags_from_message_for_display,
)
from .fetch_timeout import (  # noqa: F401
    DEFAULT_FETCH_TIMEOUT_MS,
    LOG_URL_MAX_CHARS,
    bind_abort_relay,
    build_timeout_abort_signal,
    fetch_with_timeout,
)
from .message_channel import (  # noqa: F401
    GATEWAY_CLIENT_MODES,
    GATEWAY_CLIENT_NAMES,
    INTERNAL_MESSAGE_CHANNEL,
    is_browser_copilot_client,
    is_browser_operator_ui_client,
    is_deliverable_message_channel,
    is_ephemeral_gateway_client,
    is_gateway_cli_client,
    is_gateway_message_channel,
    is_internal_message_channel,
    is_markdown_capable_message_channel,
    is_native_approval_channel,
    is_operator_ui_client,
    is_webchat_client,
    list_deliverable_message_channels,
    normalize_message_channel,
    resolve_gateway_message_channel,
    resolve_message_channel,
)
from .message_channel_constants import (  # noqa: F401
    INTERNAL_NON_DELIVERY_CHANNELS,
    internal_session_conversation_id,
    is_internal_non_delivery_channel,
)
from .normalize_secret_input import (  # noqa: F401
    normalize_optional_secret_input,
    normalize_secret_input,
)
from .parse_json_compat import parse_json_with_json5_fallback  # noqa: F401
from .provider_utils import is_reasoning_tag_provider  # noqa: F401
from .queue_helpers import (  # noqa: F401
    apply_queue_runtime_settings,
    build_queue_summary_prompt,
    count_pending_queue_items,
    drain_queue_collection,
    drain_queue_items,
    merge_queue_summary,
    preview_queue_summary_prompt,
    resolve_debounce_ms,
    should_skip_queue_item,
    summarize_dropped_queue_items,
)
from .reaction_level import (  # noqa: F401
    ReactionLevel,
    ResolvedReactionLevel,
    resolve_reaction_level,
)
from .run_with_concurrency import (  # noqa: F401
    ConcurrencyErrorMode,
    run_tasks_with_concurrency,
)
from .safe_json import safe_json_stringify  # noqa: F401
from .sleep import sleep  # noqa: F401
from .string_readers import (  # noqa: F401
    is_string_option,
    read_string_alias,
    read_string_value,
    read_trimmed_string_alias,
    strip_channel_prefix,
)
from .timer_delay import (  # noqa: F401
    MAX_SAFE_TIMEOUT_DELAY_MS,
    add_safe_timeout_delay_grace_ms,
    resolve_safe_timeout_delay_ms,
    set_safe_timeout,
)
from .token_format import format_token_count  # noqa: F401
from .transcript_tools import (  # noqa: F401
    count_tool_results,
    extract_tool_call_names,
    has_tool_call,
)
from .utf8_truncate import (  # noqa: F401
    truncate_utf8_prefix,
    truncate_utf8_suffix,
)
from .with_timeout import with_timeout  # noqa: F401
from .zod_parse import (  # noqa: F401
    safe_parse_json_with_schema,
    safe_parse_with_schema,
)
