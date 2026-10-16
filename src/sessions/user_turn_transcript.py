"""User-turn transcript helpers.

Mirrors OpenClaw's ``src/sessions/user-turn-transcript.ts``.

The module is the public surface for persisting and
shaping user-turn messages into the session transcript:

- ``resolvePersistedUserTurnText`` — channel-generated
  media placeholders are dropped only when structured
  media is present
- ``buildPersistedUserTurnMediaInputsFromFields`` —
  extract media inputs from either persisted message
  fields (``MediaPath``/``MediaPaths``/``MediaUrl``/...)
  or a pre-built media-input array
- ``buildPersistedUserTurnMessage`` — assemble the final
  user-turn message shape with media fields, sender meta,
  transport, and input provenance
- ``mergePreparedUserTurnMessageForRuntime`` — merge
  prepared (transcript-only) metadata into a runtime
  message without exposing it to the model
- ``restorePreparedUserTurnOperationalMetaForRuntime`` —
  restore only the auth state that write hooks must not
  be able to forge
- ``preparePersistedUserTurnMessageForTranscriptWrite`` —
  apply before-message hooks while preserving transcript
  metadata
- ``createUserTurnTranscriptRecorder`` — build a recorder
  state machine for an in-flight user turn; the recorder
  is the canonical handle for approve / block / fallback
  persistence

Python adaptations (documented in code):
- TS ``node:path`` → Python ``os.path``
- TS ``mimeTypeFromFilePath`` → small inline extension
  map (the full media-core MIME table is large; this port
  only needs the extension-driven fallback)
- TS ``persistSessionTranscriptTurn`` from
  ``session-accessor.ts`` is injected via the recorder's
  ``persist_turn_callback`` option; production wiring is
  the responsibility of the host
- TS string-literal union ``"inline" | "none"`` → Python
  ``Literal["inline", "none"]`` (re-exported from the
  types module)
"""
from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional, Union

from src.sessions.input_provenance import (
    apply_input_provenance_to_user_message,
    normalize_input_provenance,
)
from src.sessions.user_turn_transcript_types import (
    PersistedUserTurnMediaInput,
    PersistedUserTurnMessage,
    UserTurnInput,
    UserTurnTranscriptPersistResult,
    UserTurnTranscriptRecorder,
    UserTurnTranscriptTarget,
    UserTurnTranscriptTargetResolver,
    UserTurnTranscriptUpdateMode,
    UserTurnSender,
)

# Re-export the most-used types so callers can import them
# from this module (mirrors the TS re-export block).
__all__ = [
    "PersistedUserTurnMessage",
    "UserTurnInput",
    "UserTurnTranscriptRecorder",
    "build_persisted_user_turn_media_inputs_from_fields",
    "build_persisted_user_turn_message",
    "build_run_user_turn_idempotency_key",
    "create_user_turn_transcript_recorder",
    "merge_prepared_user_turn_message_for_runtime",
    "prepare_persisted_user_turn_message_for_transcript_write",
    "resolve_persisted_user_turn_text",
    "restore_prepared_user_turn_operational_meta_for_runtime",
    "buildPersistedUserTurnMediaInputsFromFields",
    "buildPersistedUserTurnMessage",
    "buildRunUserTurnIdempotencyKey",
    "createUserTurnTranscriptRecorder",
    "mergePreparedUserTurnMessageForRuntime",
    "preparePersistedUserTurnMessageForTranscriptWrite",
    "resolvePersistedUserTurnText",
    "restorePreparedUserTurnOperationalMetaForRuntime",
]

# Inline copy of the extension → MIME map used by
# ``mimeTypeFromFilePath``. The full OpenClaw media-core
# table is large; the recorder only needs the extension-
# driven fallback for the most common file types. Tests
# and the recorder rely on this dict being sufficient for
# the test cases.
_MIME_BY_EXT: dict[str, str] = {
    ".heic": "image/heic",
    ".heif": "image/heif",
    ".bmp": "image/bmp",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".svg": "image/svg+xml",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".ogg": "audio/ogg",
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".flac": "audio/flac",
    ".aac": "audio/aac",
    ".opus": "audio/opus",
    ".webm": "audio/webm",
    ".m4a": "audio/x-m4a",
    ".mp4": "video/mp4",
    ".mov": "video/quicktime",
    ".txt": "text/plain",
    ".json": "application/json",
}


def _mime_type_from_file_path(file_path: Optional[str]) -> Optional[str]:
    """Map a file path or URL extension to the preferred MIME type.

    Mirrors the small public surface of
    ``@openclaw/media-core/mime``'s ``mimeTypeFromFilePath``.
    """
    if not file_path:
        return None
    # ``os.path.splitext`` handles URL-like paths reasonably
    # well for the extension; the caller is responsible for
    # not passing pathologically malformed paths.
    _, ext = os.path.splitext(str(file_path))
    if not ext:
        return None
    return _MIME_BY_EXT.get(ext.lower())


# ── Constants ──────────────────────────────────────────────


CHANNEL_MEDIA_PLACEHOLDER_PATTERN = r"^<media:[a-z0-9_-]+>(?:\s+\([^)]*\))?$"
URL_LIKE_MEDIA_PATH_PATTERN = r"^[a-z][a-z0-9+.-]*:"


# ── Text helpers ───────────────────────────────────────────


def _normalize_optional_text(value: object) -> Optional[str]:
    """Trim a string value, returning ``None`` for empty / non-string.

    Mirrors the private ``normalizeOptionalText`` helper.
    """
    if not isinstance(value, str):
        return None
    trimmed = value.strip()
    return trimmed if trimmed else None


def _normalize_transcript_text(value: object) -> str:
    return value if isinstance(value, str) else ""


def build_run_user_turn_idempotency_key(run_id: str) -> str:
    """Build the canonical user-turn idempotency key for a run.

    Mirrors ``buildRunUserTurnIdempotencyKey``: returns
    ``"{runId}:user"``.
    """
    return f"{run_id}:user"


# ── Public text resolver ──────────────────────────────────


def resolve_persisted_user_turn_text(
    value: Optional[str],
    has_media: bool = False,
) -> Optional[str]:
    """Select text for persisted user turns.

    Mirrors ``resolvePersistedUserTurnText``. Channel-generated
    media placeholders (``<media:...>``) are dropped only when
    structured media is present; plain text always passes
    through.
    """
    normalized = _normalize_optional_text(value)
    if not normalized:
        return None
    if has_media:
        import re
        if re.match(CHANNEL_MEDIA_PLACEHOLDER_PATTERN, normalized, re.IGNORECASE):
            return None
    return normalized


# ── Media field assembly ─────────────────────────────────


def _media_type_for_transcript(media: PersistedUserTurnMediaInput) -> str:
    """Resolve the media MIME type for the transcript.

    Mirrors the private ``mediaTypeForTranscript`` helper.
    """
    return (
        _normalize_optional_text(media.get("contentType"))
        or _normalize_optional_text(media.get("kind"))
        or "application/octet-stream"
    )


def _normalize_media_entry_for_transcript(
    media: PersistedUserTurnMediaInput,
) -> Optional[dict[str, str]]:
    """Normalize a single media entry to ``{path, type}`` form.

    Mirrors the private ``normalizeMediaEntryForTranscript`` helper.
    """
    path_local = _normalize_optional_text(media.get("path")) or _normalize_optional_text(
        media.get("url")
    )
    if not path_local:
        return None
    return {"path": path_local, "type": _media_type_for_transcript(media)}


def _normalize_optional_text_array(
    values: object,
) -> list[Optional[str]]:
    """Map each entry to a normalized string or ``None`` (no compaction).

    Mirrors the private ``normalizeOptionalTextArray`` helper.
    The writer pads holes with ``""`` to keep parallel arrays
    index-aligned, so compaction here would shift later
    entries onto the wrong attachment.
    """
    if not isinstance(values, (list, tuple)):
        return []
    return [_normalize_optional_text(v) for v in values]


def _resolve_transcript_media_path(
    path_value: str, workspace_dir: Optional[str]
) -> str:
    """Anchor a relative staged media path to the media workspace.

    Mirrors the private ``resolveTranscriptMediaPath`` helper.
    Absolute paths and URL-like refs are returned as-is; only
    bare relative paths are joined with ``workspace_dir``.
    """
    import re
    if (
        not workspace_dir
        or os.path.isabs(path_value)
        or re.match(URL_LIKE_MEDIA_PATH_PATTERN, path_value, re.IGNORECASE)
    ):
        return path_value
    return os.path.join(workspace_dir, path_value)


def _resolve_transcript_media_type(
    *,
    explicit_type: Optional[str],
    media_path: Optional[str],
    media_url: Optional[str],
) -> Optional[str]:
    """Resolve the MIME type for a transcript media entry.

    Mirrors the private ``resolveTranscriptMediaType`` helper.
    """
    return explicit_type or _mime_type_from_file_path(media_path or media_url)


def build_persisted_user_turn_media_inputs_from_fields(
    fields: Optional[Union[dict[str, Any], PersistedUserTurnMessage]],
) -> list[PersistedUserTurnMediaInput]:
    """Extract media inputs from a persisted-message field bundle or a persisted message.

    Mirrors ``buildPersistedUserTurnMediaInputsFromFields``.
    """
    if not fields:
        return []
    media_fields = fields  # type: ignore[assignment]
    paths = _normalize_optional_text_array(media_fields.get("MediaPaths"))
    urls = _normalize_optional_text_array(media_fields.get("MediaUrls"))
    types = _normalize_optional_text_array(media_fields.get("MediaTypes"))
    single_path = _normalize_optional_text(media_fields.get("MediaPath"))
    single_url = _normalize_optional_text(media_fields.get("MediaUrl"))
    single_type = _normalize_optional_text(media_fields.get("MediaType"))
    workspace_dir = _normalize_optional_text(media_fields.get("MediaWorkspaceDir"))
    media_count = max(
        len(paths),
        len(urls),
        1 if (single_path or single_url) else 0,
    )
    media: list[PersistedUserTurnMediaInput] = []
    for index in range(media_count):
        raw_path = paths[index] if index < len(paths) else (single_path if index == 0 else None)
        media_path = (
            _resolve_transcript_media_path(raw_path, workspace_dir)
            if raw_path
            else None
        )
        url = urls[index] if index < len(urls) else (single_url if index == 0 else None)
        if not media_path and not url:
            continue
        explicit_type = types[index] if index < len(types) else (single_type if index == 0 else None)
        content_type = _resolve_transcript_media_type(
            explicit_type=explicit_type,
            media_path=media_path,
            media_url=url,
        )
        entry: PersistedUserTurnMediaInput = {}
        if media_path:
            entry["path"] = media_path
        if url:
            entry["url"] = url
        if content_type:
            entry["contentType"] = content_type
        media.append(entry)
    return media


def _build_persisted_user_turn_media_fields(
    media: Optional[list[PersistedUserTurnMediaInput]],
) -> dict[str, Any]:
    """Build the parallel ``MediaPath``/``MediaPaths`` fields.

    Mirrors the private ``buildPersistedUserTurnMediaFields`` helper.
    """
    entries = media if isinstance(media, list) else []
    normalized = [
        e
        for e in (_normalize_media_entry_for_transcript(m) for m in entries)
        if e is not None
    ]
    paths = [e["path"] for e in normalized]
    if not paths:
        return {}
    types = [e["type"] for e in normalized]
    fields: dict[str, Any] = {
        "MediaPath": paths[0],
        "MediaPaths": paths,
    }
    if types:
        fields["MediaType"] = types[0]
        fields["MediaTypes"] = types
    return fields


def _build_user_turn_sender_meta(
    sender: Optional[UserTurnSender],
) -> Optional[dict[str, str]]:
    """Build the ``__openclaw`` sender meta sub-record.

    Mirrors the private ``buildUserTurnSenderMeta`` helper.
    """
    sender_id = _normalize_optional_text(sender.get("id")) if sender else None
    sender_name = _normalize_optional_text(sender.get("name")) if sender else None
    sender_username = _normalize_optional_text(sender.get("username")) if sender else None
    if not sender_id and not sender_name and not sender_username:
        return None
    meta: dict[str, str] = {}
    if sender_id:
        meta["senderId"] = sender_id
    if sender_name:
        meta["senderName"] = sender_name
    if sender_username:
        meta["senderUsername"] = sender_username
    return meta


def _read_openclaw_message_meta(
    message: Optional[dict[str, Any]],
) -> Optional[dict[str, Any]]:
    """Read the ``__openclaw`` meta sub-record from a message.

    Mirrors the private ``readOpenClawMessageMeta`` helper.
    """
    if not message:
        return None
    meta = message.get("__openclaw")
    if not isinstance(meta, dict) or isinstance(meta, list):
        return None
    return meta


# ── Public message builder ─────────────────────────────────


def build_persisted_user_turn_message(
    params: UserTurnInput,
) -> PersistedUserTurnMessage:
    """Assemble the final user-turn message shape.

    Mirrors ``buildPersistedUserTurnMessage``. Storage is
    BARE (no timestamp prefix) — the per-message timestamp
    is added at the LLM-boundary stamping site so every
    historical turn serializes identically on the wire.
    """
    import time
    media_fields = _build_persisted_user_turn_media_fields(params.get("media"))
    text = _normalize_transcript_text(params.get("text"))
    sender_meta = _build_user_turn_sender_meta(params.get("sender"))
    openclaw_meta: dict[str, Any] = {}
    if params.get("senderIsOwner") is not None:
        openclaw_meta["senderIsOwner"] = params["senderIsOwner"]
    if sender_meta:
        openclaw_meta.update(sender_meta)
    if params.get("transport"):
        openclaw_meta["transport"] = params["transport"]
    message: dict[str, Any] = {
        "role": "user",
        "content": text,
        "timestamp": params.get("timestamp") if params.get("timestamp") is not None else int(time.time() * 1000),
    }
    if params.get("idempotencyKey"):
        message["idempotencyKey"] = params["idempotencyKey"]
    message.update(media_fields)
    if openclaw_meta:
        message["__openclaw"] = openclaw_meta
    return apply_input_provenance_to_user_message(message, params.get("provenance"))


def _resolve_persisted_user_turn_message(
    params: dict[str, Any],
) -> Optional[PersistedUserTurnMessage]:
    """Resolve the final user-turn message from ``input`` or ``message``.

    Mirrors the private ``resolvePersistedUserTurnMessage`` helper.
    """
    if params.get("message"):
        return params["message"]
    if not params.get("input"):
        return None
    return build_persisted_user_turn_message(params["input"])


# ── Runtime message helpers ────────────────────────────────


def _is_user_message(message: dict[str, Any]) -> bool:
    """Return ``True`` when ``message.role == "user"``.

    Mirrors the private ``isUserMessage`` helper.
    """
    return message.get("role") == "user"


def _is_before_agent_run_blocked_message(message: dict[str, Any]) -> bool:
    """Return ``True`` when ``message.__openclaw.beforeAgentRunBlocked`` is set.

    Mirrors the private ``isBeforeAgentRunBlockedMessage`` helper.
    """
    meta = _read_openclaw_message_meta(message)
    return meta is not None and "beforeAgentRunBlocked" in meta


def _user_message_has_image_content(message: dict[str, Any]) -> bool:
    """Return ``True`` when the message has an ``image`` content block.

    Mirrors the private ``userMessageHasImageContent`` helper.
    """
    if not _is_user_message(message):
        return False
    content = message.get("content")
    if not isinstance(content, list):
        return False
    return any(
        isinstance(block, dict)
        and not isinstance(block, list)
        and block.get("type") == "image"
        for block in content
    )


def merge_prepared_user_turn_message_for_runtime(
    *,
    runtime_message: dict[str, Any],
    prepared_message: Optional[PersistedUserTurnMessage],
) -> dict[str, Any]:
    """Merge prepared transcript metadata into a runtime message.

    Mirrors ``mergePreparedUserTurnMessageForRuntime``. Runtime
    messages may lack transcript metadata because channel
    adapters prepare display text separately. Merge only safe
    user messages, never block markers.
    """
    if (
        not prepared_message
        or not _is_user_message(runtime_message)
        or _is_before_agent_run_blocked_message(runtime_message)
    ):
        return runtime_message
    runtime_meta = _read_openclaw_message_meta(runtime_message)
    prepared_meta = _read_openclaw_message_meta(prepared_message)
    merged: dict[str, Any] = {
        **runtime_message,
        **prepared_message,
    }
    if prepared_meta is not None:
        meta: dict[str, Any] = {}
        if runtime_meta is not None:
            meta.update(runtime_meta)
        meta.update(prepared_meta)
        merged["__openclaw"] = meta
    if _user_message_has_image_content(runtime_message):
        merged["content"] = runtime_message.get("content")
    return merged


def restore_prepared_user_turn_operational_meta_for_runtime(
    *,
    runtime_message: dict[str, Any],
    prepared_message: Optional[PersistedUserTurnMessage],
) -> dict[str, Any]:
    """Restore only the auth state that write hooks must not forge or erase.

    Mirrors ``restorePreparedUserTurnOperationalMetaForRuntime``.
    """
    if not prepared_message or not _is_user_message(runtime_message):
        return runtime_message
    prepared_meta = _read_openclaw_message_meta(prepared_message)
    sender_is_owner = prepared_meta.get("senderIsOwner") if prepared_meta else None
    if not isinstance(sender_is_owner, bool):
        return runtime_message
    runtime_meta = _read_openclaw_message_meta(runtime_message)
    merged_meta: dict[str, Any] = {}
    if runtime_meta is not None:
        merged_meta.update(runtime_meta)
    merged_meta["senderIsOwner"] = sender_is_owner
    return {**runtime_message, "__openclaw": merged_meta}


# ── Before-message-write hook ────────────────────────────


def prepare_persisted_user_turn_message_for_transcript_write(
    message: PersistedUserTurnMessage,
    params: dict[str, Any],
) -> Optional[PersistedUserTurnMessage]:
    """Apply before-message hooks while preserving transcript metadata.

    Mirrors ``preparePersistedUserTurnMessageForTranscriptWrite``.
    """
    before_message_write = params.get("beforeMessageWrite")
    if not before_message_write:
        return message
    original_message = message
    idempotency_key = original_message.get("idempotencyKey")
    provenance = normalize_input_provenance(
        (message if isinstance(message, dict) else {}).get("provenance")
    )
    sender_is_owner = (_read_openclaw_message_meta(message) or {}).get("senderIsOwner")
    original_transport = (_read_openclaw_message_meta(message) or {}).get("transport")
    transport: Optional[dict[str, Any]] = None
    if (
        original_transport
        and isinstance(original_transport, dict)
        and not isinstance(original_transport, list)
    ):
        transport = {**original_transport}
    next_message = before_message_write(
        {
            "message": message,
            **({"agentId": params["agentId"]} if params.get("agentId") else {}),
            **({"sessionKey": params["sessionKey"]} if params.get("sessionKey") else {}),
        }
    )
    if not next_message or next_message.get("role") != "user":
        return None
    next_user_message = (
        apply_input_provenance_to_user_message(next_message, provenance)
        if provenance
        else next_message
    )
    if not idempotency_key and not isinstance(sender_is_owner, bool) and not transport:
        return next_user_message
    protected_meta: dict[str, Any] = {
        **(_read_openclaw_message_meta(next_user_message) or {}),
    }
    if isinstance(sender_is_owner, bool):
        protected_meta["senderIsOwner"] = sender_is_owner
    if transport:
        protected_meta["transport"] = transport
    out: dict[str, Any] = {**next_user_message}
    if idempotency_key:
        out["idempotencyKey"] = idempotency_key
    if protected_meta:
        out["__openclaw"] = protected_meta
    return out


# ── Late-resolved media merge ─────────────────────────────


def _build_late_resolved_media_message(
    *,
    admitted_message: Optional[PersistedUserTurnMessage],
    resolved_message: PersistedUserTurnMessage,
) -> Optional[PersistedUserTurnMessage]:
    """Build a follow-up message for media resolved after admission.

    Mirrors the private ``buildLateResolvedMediaMessage`` helper.
    When the resolved message has new media the admitted
    message did not, persist the new media as a second turn
    so the inline replacement does not thrash the cache tail.
    """
    admitted_media = build_persisted_user_turn_media_inputs_from_fields(
        admitted_message
    )
    resolved_media = build_persisted_user_turn_media_inputs_from_fields(
        resolved_message
    )
    if (
        not resolved_media
        or json.dumps(resolved_media, sort_keys=True)
        == json.dumps(admitted_media, sort_keys=True)
    ):
        return None
    resolved = resolved_message if isinstance(resolved_message, dict) else {}
    admitted_content = (
        admitted_message.get("content") if isinstance(admitted_message, dict) else None
    )
    resolved_content = resolved.get("content")
    media_only_text = "\n".join(
        f"[media attached: {m.get('path') or m.get('url')}]"
        for m in resolved_media
        if m.get("path") or m.get("url")
    )
    if (
        isinstance(resolved_content, str)
        and resolved_content == admitted_content
    ):
        content: Any = media_only_text
    elif isinstance(resolved_content, list) and isinstance(admitted_content, str):
        media_content = [
            block
            for block in resolved_content
            if not block
            or not isinstance(block, dict)
            or block.get("type") != "text"
            or block.get("text") != admitted_content
        ]
        if media_content:
            content = media_content
        else:
            content = [{"type": "text", "text": media_only_text}]
    else:
        content = resolved_content
    import time

    idempotency_key = (
        f"{resolved.get('idempotencyKey')}:late-media"
        if isinstance(resolved.get("idempotencyKey"), str)
        and resolved.get("idempotencyKey")
        else f"late-media:{resolved.get('timestamp') if isinstance(resolved.get('timestamp'), (int, float)) else int(time.time() * 1000)}"
    )
    return {**resolved, "content": content, "idempotencyKey": idempotency_key}


# ── Recorder ─────────────────────────────────────────────


PersistTurnCallback = Callable[..., Awaitable[dict[str, Any]]]


@dataclass
class _RecorderOptions:
    """Internal recorder options (subset of CreateUserTurnTranscriptRecorderParams)."""

    target: Optional[UserTurnTranscriptTargetResolver] = None
    update_mode: UserTurnTranscriptUpdateMode = "inline"
    before_message_write: Optional[Callable[..., Any]] = None
    error_context: Optional[str] = None
    on_persistence_error: Optional[Callable[[Any], None]] = None
    on_message_persisted: Optional[Callable[[PersistedUserTurnMessage], Any]] = None
    expected_session_state: Optional[dict[str, Any]] = None
    session_lifecycle_patch: Optional[dict[str, Any]] = None
    persist_turn_callback: Optional[PersistTurnCallback] = None


def create_user_turn_transcript_recorder(
    params: dict[str, Any],
) -> UserTurnTranscriptRecorder:
    """Build a recorder state machine for an in-flight user turn.

    Mirrors ``createUserTurnTranscriptRecorder``. The
    recorder is the canonical handle for approve / block /
    fallback persistence. The host wires the actual store
    writer via the ``persist_turn_callback`` option
    (``params["persistTurnCallback"]``); the callback
    receives the same shape OpenClaw passes to
    ``persistSessionTranscriptTurn``.
    """
    message = _resolve_persisted_user_turn_message(params)
    options = _RecorderOptions(
        target=params.get("target"),
        update_mode=params.get("updateMode", "inline"),
        before_message_write=params.get("beforeMessageWrite"),
        error_context=params.get("errorContext"),
        on_persistence_error=params.get("onPersistenceError"),
        on_message_persisted=params.get("onMessagePersisted"),
        expected_session_state=params.get("expectedSessionState"),
        session_lifecycle_patch=params.get("sessionLifecyclePatch"),
        persist_turn_callback=params.get("persistTurnCallback"),
    )

    state: dict[str, Any] = {
        "blocked": False,
        "persisted": False,
        "runtime_persisted": False,
        "persisted_result": None,
        "persistence_promise": None,
        "self_persistence_promise": None,
        "self_persistence_result": None,
        "self_persistence_running": False,
        "resolved_message_promise": None,
        "persisted_message_notified": False,
        "runtime_persisted_message": None,
        "sent_to_provider": False,
        "resolved_before_provider": False,
    }

    def _handle_persistence_error(error: Any) -> None:
        if options.on_persistence_error is not None:
            options.on_persistence_error(error)
            return
        # Production code paths route through the host
        # logger; tests inject their own onPersistenceError.
        # The default behavior is to swallow the error so the
        # host's main flow is not broken.

    async def _resolve_message_for_persistence() -> Optional[PersistedUserTurnMessage]:
        if params.get("message"):
            return params["message"]
        if not params.get("resolveInput"):
            return message
        if not state["resolved_message_promise"]:
            async def _resolve_inner() -> Optional[PersistedUserTurnMessage]:
                try:
                    resolved_input = await params["resolveInput"]()
                    resolved_message = (
                        _resolve_persisted_user_turn_message(
                            {
                                "message": params.get("message"),
                                "input": resolved_input or params.get("input"),
                            }
                        )
                        or message
                    )
                    state["resolved_before_provider"] = not state["sent_to_provider"]
                    return resolved_message
                except Exception as error:  # noqa: BLE001
                    _handle_persistence_error(error)
                    return message

            state["resolved_message_promise"] = _resolve_inner()
        return await state["resolved_message_promise"]

    def _notify_message_persisted(persisted_message: Optional[PersistedUserTurnMessage]) -> None:
        if state["persisted_message_notified"]:
            return
        notification_message = (
            persisted_message
            or (state["persisted_result"] or {}).get("message")
            or message
        )
        if not notification_message or not options.on_message_persisted:
            return
        state["persisted_message_notified"] = True
        try:
            result = options.on_message_persisted(notification_message)
            if result is not None:
                import asyncio

                try:
                    loop = asyncio.get_event_loop()
                    loop.create_task(result)
                except RuntimeError:
                    import asyncio as _asyncio
                    _asyncio.run(result)
        except Exception as error:  # noqa: BLE001
            _handle_persistence_error(error)

    async def _wait_for_runtime_persistence() -> None:
        if not state["persistence_promise"]:
            return
        try:
            await state["persistence_promise"]
        except Exception as error:  # noqa: BLE001
            _handle_persistence_error(error)

    async def _resolve_target(
        resolver: Optional[UserTurnTranscriptTargetResolver],
    ) -> Optional[UserTurnTranscriptTarget]:
        if resolver is None:
            return None
        if callable(resolver):
            result = resolver()
            if hasattr(result, "__await__"):
                result = await result
            return result  # type: ignore[return-value]
        return resolver  # type: ignore[return-value]

    async def _persist_prepared(opts: dict[str, Any]) -> Optional[UserTurnTranscriptPersistResult]:
        if opts.get("skip_when_blocked") and state["blocked"]:
            return None
        if not opts.get("message") and not message and not params.get("resolveInput"):
            return None
        if opts.get("wait_for_runtime"):
            await _wait_for_runtime_persistence()
        if state["self_persistence_running"]:
            # Another persistPrepared call is in flight;
            # wait for it to complete and return its result.
            while state["self_persistence_running"]:
                await asyncio.sleep(0)
            return state["self_persistence_result"]
        if state["self_persistence_result"] is not None or state["persisted"]:
            return state["self_persistence_result"] or state["persisted_result"]

        async def _inner() -> Optional[UserTurnTranscriptPersistResult]:
            resolved_message = opts.get("message") or await _resolve_message_for_persistence()
            if not resolved_message:
                return None
            target = await _resolve_target(opts.get("target") or options.target)
            if not target:
                return None
            resolved_target: dict[str, Any] = (
                {**target, "cwd": opts["cwd"]} if opts.get("cwd") else target
            )
            update_mode = opts.get("update_mode") or options.update_mode or "inline"

            async def _persist_message(
                candidate: PersistedUserTurnMessage,
                candidate_update_mode: UserTurnTranscriptUpdateMode,
            ) -> Optional[UserTurnTranscriptPersistResult]:
                if options.persist_turn_callback is None:
                    return None
                payload: dict[str, Any] = {
                    **resolved_target,
                    "message": candidate,
                    "updateMode": candidate_update_mode,
                }
                if opts.get("expected_session_id"):
                    payload["expectedSessionId"] = opts["expected_session_id"]
                patch = opts.get("session_lifecycle_patch") or options.session_lifecycle_patch
                if patch:
                    payload["sessionLifecyclePatch"] = patch
                state_obj = opts.get("expected_session_state") or options.expected_session_state
                if state_obj:
                    payload["expectedSessionState"] = state_obj
                if options.before_message_write:
                    payload["beforeMessageWrite"] = options.before_message_write
                return await options.persist_turn_callback(payload)

            late_media_message = (
                _build_late_resolved_media_message(
                    admitted_message=state["runtime_persisted_message"] or message,
                    resolved_message=resolved_message,
                )
                if state["sent_to_provider"] and not state["resolved_before_provider"]
                else None
            )
            if late_media_message:
                if not state["runtime_persisted"] and not state["persisted"] and message:
                    admitted_result = await _persist_message(message, update_mode)
                    if admitted_result:
                        state["persisted"] = True
                        state["persisted_result"] = admitted_result
                        _notify_message_persisted(admitted_result.get("message"))
                appended_media = await _persist_message(late_media_message, "none")
                if appended_media:
                    state["persisted"] = True
                    state["persisted_result"] = appended_media
                return appended_media
            if state["runtime_persisted"]:
                return None
            if state["persisted"]:
                return state["persisted_result"]
            result = await _persist_message(resolved_message, update_mode)
            if result:
                state["persisted"] = True
                state["persisted_result"] = result
                _notify_message_persisted(result.get("message"))
            return result

        state["self_persistence_promise"] = _inner()
        state["self_persistence_running"] = True
        try:
            result = await state["self_persistence_promise"]
            state["self_persistence_result"] = result
            return result
        except Exception as error:  # noqa: BLE001
            _handle_persistence_error(error)
            raise
        finally:
            state["self_persistence_running"] = False

    return {
        "message": message,
        "resolveMessage": _resolve_message_for_persistence,
        "getPersistedMessage": lambda: state["runtime_persisted_message"]
        or (state["persisted_result"] or {}).get("message"),
        "markSentToProvider": lambda: state.__setitem__("sent_to_provider", True),
        "markRuntimePersistencePending": lambda pending: state.__setitem__(
            "persistence_promise", pending
        ),
        "markRuntimePersisted": lambda persisted_message: (
            state.__setitem__("runtime_persisted_message", persisted_message),
            state.__setitem__("runtime_persisted", True),
            (
                state.__setitem__(
                    "persisted_result",
                    {
                        **state["persisted_result"],
                        "message": persisted_message,
                    },
                )
                if persisted_message and state["persisted_result"]
                else None
            ),
            _notify_message_persisted(persisted_message),
        ),
        "markBlocked": lambda: state.__setitem__("blocked", True),
        "hasPersisted": lambda: bool(state["persisted"] or state["runtime_persisted"]),
        "isBlocked": lambda: bool(state["blocked"]),
        "hasRuntimePersistencePending": lambda: state["persistence_promise"] is not None,
        "waitForRuntimePersistence": _wait_for_runtime_persistence,
        "persistApproved": lambda options_arg=None: _persist_prepared(
            {
                "wait_for_runtime": False,
                "skip_when_blocked": True,
                "target": (options_arg or {}).get("target"),
                "update_mode": (options_arg or {}).get("updateMode"),
                "cwd": (options_arg or {}).get("cwd"),
                "expected_session_id": (options_arg or {}).get("expectedSessionId"),
                "expected_session_state": (options_arg or {}).get("expectedSessionState"),
                "session_lifecycle_patch": (options_arg or {}).get("sessionLifecyclePatch"),
            }
        ),
        "persistBlocked": lambda blocked_message, options_arg=None: (
            state.__setitem__("blocked", True),
            _persist_prepared(
                {
                    "wait_for_runtime": False,
                    "skip_when_blocked": False,
                    "message": blocked_message,
                    "target": (options_arg or {}).get("target"),
                    "update_mode": (options_arg or {}).get("updateMode"),
                    "cwd": (options_arg or {}).get("cwd"),
                }
            ),
        )[1],
        "persistFallback": lambda options_arg=None: _persist_prepared(
            {
                "wait_for_runtime": True,
                "skip_when_blocked": True,
                "target": (options_arg or {}).get("target"),
                "update_mode": (options_arg or {}).get("updateMode"),
                "cwd": (options_arg or {}).get("cwd"),
            }
        ),
    }


# OpenClaw camelCase parity aliases:
buildPersistedUserTurnMediaInputsFromFields = build_persisted_user_turn_media_inputs_from_fields
buildPersistedUserTurnMessage = build_persisted_user_turn_message
buildRunUserTurnIdempotencyKey = build_run_user_turn_idempotency_key
createUserTurnTranscriptRecorder = create_user_turn_transcript_recorder
mergePreparedUserTurnMessageForRuntime = merge_prepared_user_turn_message_for_runtime
preparePersistedUserTurnMessageForTranscriptWrite = prepare_persisted_user_turn_message_for_transcript_write
resolvePersistedUserTurnText = resolve_persisted_user_turn_text
restorePreparedUserTurnOperationalMetaForRuntime = restore_prepared_user_turn_operational_meta_for_runtime

