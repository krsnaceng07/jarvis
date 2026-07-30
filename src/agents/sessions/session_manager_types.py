"""jarvis.agents.sessions.session_manager_types — session entry types.

OpenClaw parity: mirrors
``openclaw-main/src/agents/sessions/session-manager-types.ts``.

The session-file entry types: header, message,
thinking-level change, model change, compaction,
branch summary, custom (opaque + visible), label,
session info. Every entry is keyed by ``id`` +
``parentId`` so the runtime can build a transcript
tree.

Parity
======
- ``SessionHeader`` (``session-manager-types.ts:9-16``)
  — the leading ``type: "session"`` line.
- ``NewSessionOptions`` (``:18-21``) — the
  ``create_session`` call args.
- ``SessionEntryBase`` (``:23-30``) — the shared
  fields every entry has.
- ``SessionMessageEntry`` (``:32-35``) — a
  conversation message (user / assistant / tool
  result / bash execution / branch summary /
  compaction summary / custom).
- ``ThinkingLevelChangeEntry`` (``:37-40``) —
  records a thinking-level change mid-session.
- ``ModelChangeEntry`` (``:42-46``) — records a
  model change.
- ``CompactionEntry[T]`` (``:48-57``) — a
  compaction with summary + first-kept-entry pointer.
- ``BranchSummaryEntry[T]`` (``:59-67``) — a
  branch summary (used for fork + fold).
- ``CustomEntry[T]`` (``:70-74``) — opaque
  extension state excluded from model context.
- ``LabelEntry`` (``:76-80``) — user-set label
  on an entry.
- ``SessionInfoEntry`` (``:82-85``) — session name
  metadata.
- ``CustomMessageEntry[T]`` (``:88-94``) —
  extension message that participates in model
  context.
- ``SessionEntry`` discriminated union (``:96-105``).
- ``FileEntry`` union (``:107``).
- ``AppendPersistenceOptions`` (``:109-113``) —
  options for ``append_entry``-style writes.
- ``SessionTreeNode`` (``:115-120``) — a single
  node in the session tree.
- ``SessionContext`` (``:122-126``) — the
  ``build_session_context`` return shape.
- ``SessionInfo`` (``:128-140``) — the list-view
  shape.
- ``SessionListProgress`` (``:142``) — list
  callback type.
- ``PromptReleasedOpaqueEntry`` (private, ``:144-148``).
- ``PromptReleasedSessionEntry`` (``:150-155``) —
  the entries a prompt-released replayer accepts.
- ``PromptReleasedSessionMergeResult`` (``:157-161``) —
  the merge result.
- ``SessionFileSnapshot`` (``:163``) — alias for
  the transcript cache snapshot.
- ``PreservedOpaqueFileEntry`` (``:165-168``) —
  an opaque entry preserved by the replayer.
- ``SessionLeafControl`` (``:170-177``) — the
  leaf-control entry the tree-resolver consumes.

Phase 6.2 — session codec.

Adaptations
-----------
- The OpenClaw source imports the
  ``OwnedSessionTranscriptCacheSnapshot`` /
  ``OwnedSessionTranscriptPublishedEntry`` types
  from ``config/sessions/transcript-write-context.ts``.
  The Python port declares the *shape* of these
  types as ``dict[str, object]`` (the
  configuration-side port lands in Phase 6.4).
  Consumers type-hint them as
  ``SessionFileSnapshot`` / ``PromptReleasedSessionMergeResult``
  with the same OpenClaw field names.
- The OpenClaw source uses string-literal unions
  (``"message" | "thinking_level_change" | ...``)
  in the ``type`` discriminator. The Python port
  uses the same literals in :class:`typing.Literal`
  types; the union is exposed as a
  ``TypeAlias`` so callers can write
  ``SessionEntry`` directly.
- Generic parameters (``CompactionEntry<T>``) are
  preserved as Python ``Generic`` dataclasses;
  the default ``T = object`` matches the OpenClaw
  default (``T = unknown`` in TS).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import (
    Any,
    Callable,
    Generic,
    Literal,
    Optional,
    TypeAlias,
    TypeVar,
    Union,
)

from jarvis_agent.types import (
    AgentMessage,
    ImageContent,
    TextContent,
)


#: Generic for the ``details`` / ``data`` payload on
#: custom / compaction / branch-summary entries. Matches
#: the OpenClaw ``T = unknown`` default.
T = TypeVar("T")


#: Discriminated entry-type literal. Mirrors the
#: ``isSessionEntryType`` switch in
#: ``session-manager-codec.ts:189-204``.
SessionEntryType = Literal[
    "message",
    "thinking_level_change",
    "model_change",
    "compaction",
    "branch_summary",
    "custom",
    "custom_message",
    "label",
    "session_info",
]


# ============================================================================
# SessionHeader — the leading ``type: "session"`` line
# ============================================================================


@dataclass(frozen=True, slots=True)
class SessionHeader:
    """Mirrors ``SessionHeader``
    (``session-manager-types.ts:9-16``).

    The first line of every session file. Holds
    the canonical session id, the timestamp at
    which the session was created, the working
    directory, the optional parent session
    (for forks), and a ``version`` integer used
    by the schema-migration system.
    """

    id: str
    timestamp: str
    cwd: str
    parent_session: Optional[str] = None
    version: Optional[int] = None
    type: Literal["session"] = "session"


# ============================================================================
# NewSessionOptions — create_session call args
# ============================================================================


@dataclass(frozen=True, slots=True)
class NewSessionOptions:
    """Mirrors ``NewSessionOptions``
    (``session-manager-types.ts:18-21``)."""

    id: Optional[str] = None
    parent_session: Optional[str] = None


# ============================================================================
# SessionEntryBase — shared fields
# ============================================================================


@dataclass(frozen=True, slots=True)
class SessionEntryBase:
    """Mirrors ``SessionEntryBase``
    (``session-manager-types.ts:23-30``).

    Every session entry has a ``type`` discriminator,
    an ``id``, a ``parentId`` (null for the root),
    and a ``timestamp``. The optional ``appendMode``
    flags entries that consume the raw side cursor
    instead of the visible leaf (used by the
    transcript tree's leaf-control).
    """

    id: str
    parent_id: Optional[str]
    timestamp: str
    type: str = "session"
    append_mode: Optional[Literal["side"]] = None


# ============================================================================
# SessionMessageEntry — conversation message
# ============================================================================


@dataclass(frozen=True, slots=True)
class SessionMessageEntry(SessionEntryBase):
    """Mirrors ``SessionMessageEntry``
    (``session-manager-types.ts:32-35``)."""

    message: Optional[AgentMessage] = None
    type: Literal["message"] = "message"


# ============================================================================
# ThinkingLevelChangeEntry
# ============================================================================


@dataclass(frozen=True, slots=True)
class ThinkingLevelChangeEntry(SessionEntryBase):
    """Mirrors ``ThinkingLevelChangeEntry``
    (``session-manager-types.ts:37-40``)."""

    thinking_level: str = ""
    type: Literal["thinking_level_change"] = "thinking_level_change"


# ============================================================================
# ModelChangeEntry
# ============================================================================


@dataclass(frozen=True, slots=True)
class ModelChangeEntry(SessionEntryBase):
    """Mirrors ``ModelChangeEntry``
    (``session-manager-types.ts:42-46``)."""

    provider: str = ""
    model_id: str = ""
    type: Literal["model_change"] = "model_change"


# ============================================================================
# CompactionEntry[T]
# ============================================================================


@dataclass(frozen=True, slots=True)
class CompactionEntry(SessionEntryBase, Generic[T]):
    """Mirrors ``CompactionEntry<T = unknown>``
    (``session-manager-types.ts:48-57``).

    Records a compaction with a summary of the
    dropped history, a pointer to the first entry
    that survived the compaction, the token count
    before the compaction, optional extension-
    specific ``details``, and a flag indicating
    that the compaction was generated by a hook
    (rather than the runtime's manual / threshold
    flow).
    """

    summary: str = ""
    first_kept_entry_id: str = ""
    tokens_before: int = 0
    details: Optional[T] = None
    from_hook: Optional[bool] = None
    type: Literal["compaction"] = "compaction"


# ============================================================================
# BranchSummaryEntry[T]
# ============================================================================


@dataclass(frozen=True, slots=True)
class BranchSummaryEntry(SessionEntryBase, Generic[T]):
    """Mirrors ``BranchSummaryEntry<T = unknown>``
    (``session-manager-types.ts:59-67``)."""

    from_id: str = ""
    summary: str = ""
    details: Optional[T] = None
    from_hook: Optional[bool] = None
    type: Literal["branch_summary"] = "branch_summary"


# ============================================================================
# CustomEntry[T]
# ============================================================================


@dataclass(frozen=True, slots=True)
class CustomEntry(SessionEntryBase, Generic[T]):
    """Mirrors ``CustomEntry<T = unknown>``
    (``session-manager-types.ts:70-74``)."""

    custom_type: str = ""
    data: Optional[T] = None
    type: Literal["custom"] = "custom"


# ============================================================================
# LabelEntry
# ============================================================================


@dataclass(frozen=True, slots=True)
class LabelEntry(SessionEntryBase):
    """Mirrors ``LabelEntry``
    (``session-manager-types.ts:76-80``)."""

    target_id: str = ""
    label: Optional[str] = None
    type: Literal["label"] = "label"


# ============================================================================
# SessionInfoEntry
# ============================================================================


@dataclass(frozen=True, slots=True)
class SessionInfoEntry(SessionEntryBase):
    """Mirrors ``SessionInfoEntry``
    (``session-manager-types.ts:82-85``)."""

    name: Optional[str] = None
    type: Literal["session_info"] = "session_info"


# ============================================================================
# CustomMessageEntry[T]
# ============================================================================


@dataclass(frozen=True, slots=True)
class CustomMessageEntry(SessionEntryBase, Generic[T]):
    """Mirrors ``CustomMessageEntry<T = unknown>``
    (``session-manager-types.ts:88-94``)."""

    custom_type: str = ""
    content: Union[str, list[Union[TextContent, ImageContent]]] = field(
        default_factory=list
    )
    display: bool = False
    details: Optional[T] = None
    type: Literal["custom_message"] = "custom_message"


# ============================================================================
# Discriminated union: SessionEntry
# ============================================================================


#: The discriminated union of every session entry.
#: Mirrors ``SessionEntry``
#: (``session-manager-types.ts:96-105``). The
#: Python port uses a ``TypeAlias`` for the union
#: so type-checkers + runtime both honour the
#: discriminator on the ``type`` field.
SessionEntry: TypeAlias = Union[
    SessionMessageEntry,
    ThinkingLevelChangeEntry,
    ModelChangeEntry,
    CompactionEntry[Any],
    BranchSummaryEntry[Any],
    CustomEntry[Any],
    CustomMessageEntry[Any],
    LabelEntry,
    SessionInfoEntry,
]


# ============================================================================
# FileEntry — the on-disk shape (header + entries)
# ============================================================================


#: The shape persisted to disk. Mirrors ``FileEntry``
#: (``session-manager-types.ts:107``) — the union of
#: the leading ``SessionHeader`` and the per-entry
#: ``SessionEntry`` variants.
FileEntry: TypeAlias = Union[SessionHeader, SessionEntry]


# ============================================================================
# AppendPersistenceOptions
# ============================================================================


@dataclass(frozen=True, slots=True)
class AppendPersistenceOptions:
    """Mirrors ``AppendPersistenceOptions``
    (``session-manager-types.ts:109-113``)."""

    config: Optional[Any] = None
    idempotency_lookup: Optional[
        Literal["scan", "scan-assistant", "caller-checked"]
    ] = None
    invalidate_serialized_prefix_cache: Optional[bool] = None


# ============================================================================
# SessionTreeNode
# ============================================================================


@dataclass(frozen=True)
class SessionTreeNode:
    """Mirrors ``SessionTreeNode``
    (``session-manager-types.ts:115-120``)."""

    entry: Any  # SessionEntry — kept loose to avoid circular import
    children: list["SessionTreeNode"] = field(default_factory=list)
    label: Optional[str] = None
    label_timestamp: Optional[str] = None


# ============================================================================
# SessionContext
# ============================================================================


@dataclass(frozen=True, slots=True)
class SessionContext:
    """Mirrors ``SessionContext``
    (``session-manager-types.ts:122-126``)."""

    messages: list[AgentMessage] = field(default_factory=list)
    thinking_level: str = "off"
    model: Optional[dict] = None  # {provider, modelId}


# ============================================================================
# SessionInfo
# ============================================================================


@dataclass(frozen=True, slots=True)
class SessionInfo:
    """Mirrors ``SessionInfo``
    (``session-manager-types.ts:128-140``)."""

    path: str = ""
    id: str = ""
    cwd: str = ""
    name: Optional[str] = None
    parent_session_path: Optional[str] = None
    created: Optional[Any] = None  # datetime
    modified: Optional[Any] = None  # datetime
    message_count: int = 0
    first_message: str = ""
    all_messages_text: str = ""


# ============================================================================
# SessionListProgress callback
# ============================================================================


#: ``SessionListProgress = (loaded, total) -> None``.
#: Mirrors ``SessionListProgress``
#: (``session-manager-types.ts:142``).
SessionListProgress: TypeAlias = Callable[[int, int], None]


# ============================================================================
# PromptReleasedOpaqueEntry (private) + PromptReleasedSessionEntry
# ============================================================================


@dataclass(frozen=True, slots=True)
class _PromptReleasedOpaqueEntry:
    """Mirrors the private
    ``PromptReleasedOpaqueEntry``
    (``session-manager-types.ts:144-148``)."""

    record: Any = None
    preserve_active_leaf: Optional[bool] = None
    type: Literal["prompt_released_opaque"] = "prompt_released_opaque"


#: The set of entries a prompt-released replayer
#: accepts. Mirrors ``PromptReleasedSessionEntry``
#: (``session-manager-types.ts:150-155``).
PromptReleasedSessionEntry: TypeAlias = Union[
    SessionMessageEntry,
    CustomEntry[Any],
    LabelEntry,
    SessionInfoEntry,
    _PromptReleasedOpaqueEntry,
]


# ============================================================================
# PromptReleasedSessionMergeResult
# ============================================================================


@dataclass(frozen=True, slots=True)
class PromptReleasedSessionMergeResult:
    """Mirrors ``PromptReleasedSessionMergeResult``
    (``session-manager-types.ts:157-161``)."""

    session_file_snapshot: Optional[Any] = None
    published_entries: Optional[list] = None
    requires_reload: Optional[bool] = None


# ============================================================================
# SessionFileSnapshot
# ============================================================================


#: Alias for the transcript cache snapshot. Mirrors
#: ``SessionFileSnapshot``
#: (``session-manager-types.ts:163``) — the
#: full type is owned by the configuration-side
#: transcript cache; the Python port declares the
#: alias as ``Any`` (Phase 6.4 ports the concrete
#: shape).
SessionFileSnapshot: TypeAlias = Any


# ============================================================================
# PreservedOpaqueFileEntry
# ============================================================================


@dataclass(frozen=True, slots=True)
class PreservedOpaqueFileEntry:
    """Mirrors ``PreservedOpaqueFileEntry``
    (``session-manager-types.ts:165-168``)."""

    index: int = 0
    record: Any = None


# ============================================================================
# SessionLeafControl
# ============================================================================


@dataclass(frozen=True, slots=True)
class SessionLeafControl:
    """Mirrors ``SessionLeafControl``
    (``session-manager-types.ts:170-177``)."""

    id: str = ""
    parent_id: Optional[str] = None
    timestamp: str = ""
    target_id: Optional[str] = None
    append_parent_id: Optional[str] = None
    append_mode: Optional[Literal["side"]] = None
    type: Literal["leaf"] = "leaf"


__all__ = [
    "AppendPersistenceOptions",
    "BranchSummaryEntry",
    "CompactionEntry",
    "CustomEntry",
    "CustomMessageEntry",
    "FileEntry",
    "LabelEntry",
    "ModelChangeEntry",
    "NewSessionOptions",
    "PreservedOpaqueFileEntry",
    "PromptReleasedSessionEntry",
    "PromptReleasedSessionMergeResult",
    "SessionContext",
    "SessionEntry",
    "SessionEntryType",
    "SessionFileSnapshot",
    "SessionHeader",
    "SessionInfo",
    "SessionInfoEntry",
    "SessionLeafControl",
    "SessionListProgress",
    "SessionMessageEntry",
    "SessionTreeNode",
    "ThinkingLevelChangeEntry",
]
