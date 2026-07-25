"""jarvis_agent.harness_types — session-tree and harness contracts.

OpenClaw parity: ``packages/agent-core/src/harness/types.ts``.

The session tree
================
A session is an append-only tree of entries, not a flat list. Each entry
names its parent by id, ``None`` marking a root. Branching a conversation
means appending a new child to an older parent rather than rewriting
history, so an entry is never mutated or deleted once written.

Ordering is by id, not by an explicit sequence column — see
:mod:`jarvis_agent.uuid7` for why that works and what breaks if ids stop
being monotonic.

``append_mode="side"`` marks an entry that must not become the new leaf:
metadata like a label or a session rename is recorded beside the transcript
rather than extending it. Ignoring the flag would make a rename look like a
conversation turn.

Timestamps are ISO strings here
===============================
``SessionTreeEntry.timestamp`` is a ``str``, while the message types in
:mod:`jarvis_agent.types` use millisecond ints. That mismatch is in
OpenClaw and is deliberate: tree entries are a persistence format meant to
stay readable, messages are an in-memory format meant to be cheap to
compare. :mod:`jarvis_agent.messages` owns the conversion, and
``require_session_timestamp_ms`` / ``parse_session_timestamp_ms`` are the
two ways to cross it.

Result divergence — read this before using ``Result``
=====================================================
OpenClaw's harness re-exports ``ok`` / ``err`` / ``Result`` from
``normalization-core``, where ``Result<TValue, TError>`` is generic over the
error type. The harness relies on that: it returns
``err(CompactionError(...))``, passing an exception *object* as the error.

JARVIS already has a ``Result`` in ``jarvis_normalization_core.result``, but it is a
narrower thing — ``Err(error: str, code: str)`` — designed for the plugin
wire format, where an error has to serialize to text. It cannot carry a
``CompactionError``.

So this module defines the faithful generic form rather than bending either
side. The two are intentionally separate:

* :class:`jarvis_normalization_core.result.Result` — plugin boundary, string errors.
* this module's :data:`Result` — harness internals, typed error objects.

Unifying them is a real cleanup, but it changes the published plugin
contract, so it belongs in a phase of its own rather than smuggled in here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Generic, Literal, TypeAlias, TypeVar, Union

from jarvis_llm.types import ImageContent, TextContent

from .types import AgentMessage

TValue = TypeVar("TValue")
TError = TypeVar("TError")


# ─────────────────────────────────────────────────────────────────────
# Result
# ─────────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class Ok(Generic[TValue]):
    """Successful result. Parity: ``{ ok: true; value }``.

    The field is named ``ok`` to match the TS discriminant, so a
    round-tripped JSON payload keeps the same shape.
    """

    value: TValue
    ok: Literal[True] = True


@dataclass(frozen=True, slots=True)
class Err(Generic[TError]):
    """Failed result. Parity: ``{ ok: false; error }``.

    ``error`` is any value, typically a :class:`CompactionError` or
    :class:`BranchSummaryError` instance. It is *not* a string — the whole
    reason this type exists separately from ``jarvis_normalization_core.result.Err``.
    """

    error: TError
    ok: Literal[False] = False


#: Parity: ``Result<TValue, TError>``.
Result: TypeAlias = Union[Ok[Any], Err[Any]]


def ok(value: TValue) -> Ok[TValue]:
    """Create a successful result. Parity: ``ok()``."""
    return Ok(value=value)


def err(error: TError) -> Err[TError]:
    """Create a failed result. Parity: ``err()``."""
    return Err(error=error)


# ─────────────────────────────────────────────────────────────────────
# Errors
# ─────────────────────────────────────────────────────────────────────

#: Parity: ``CompactionErrorCode``.
CompactionErrorCode: TypeAlias = Literal[
    "aborted", "summarization_failed", "invalid_session", "unknown"
]

#: Parity: ``BranchSummaryErrorCode``. Note it has no ``"unknown"`` arm,
#: unlike compaction. The narrower set is preserved rather than unified:
#: a branch summary failure always has an identifiable cause.
BranchSummaryErrorCode: TypeAlias = Literal["aborted", "summarization_failed", "invalid_session"]


class CompactionError(Exception):
    """Parity: ``CompactionError``.

    Carried as the error value of an :class:`Err`, not raised — compaction
    failure is an expected outcome the caller must handle (usually by
    keeping the uncompacted transcript), not an exception to propagate.

    ``cause`` mirrors the TS ``{ cause }`` option and is also chained via
    ``__cause__`` so a traceback shows it if this ever is raised.
    """

    def __init__(
        self,
        code: CompactionErrorCode,
        message: str,
        cause: BaseException | None = None,
    ) -> None:
        super().__init__(message)
        #: Parity: ``this.code``.
        self.code: CompactionErrorCode = code
        #: Parity: ``this.name = "CompactionError"``.
        self.name = "CompactionError"
        #: Parity: the ``cause`` constructor option.
        self.cause = cause
        if cause is not None:
            self.__cause__ = cause


class BranchSummaryError(Exception):
    """Parity: ``BranchSummaryError``. Same contract as :class:`CompactionError`."""

    def __init__(
        self,
        code: BranchSummaryErrorCode,
        message: str,
        cause: BaseException | None = None,
    ) -> None:
        super().__init__(message)
        #: Parity: ``this.code``.
        self.code: BranchSummaryErrorCode = code
        #: Parity: ``this.name = "BranchSummaryError"``.
        self.name = "BranchSummaryError"
        self.cause = cause
        if cause is not None:
            self.__cause__ = cause


# ─────────────────────────────────────────────────────────────────────
# Session tree entries
# ─────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class SessionTreeEntryBase:
    """Fields shared by every entry. Parity: ``SessionTreeEntryBase``.

    Not part of the public union — the ten concrete variants below are.
    """

    #: Entry id. Monotonic UUIDv7, so id order is transcript order.
    id: str = ""
    #: Parent entry id, ``None`` for a root.
    parent_id: str | None = None
    #: ISO-8601 timestamp string. See the module docstring on why not an int.
    timestamp: str = ""
    #: ``"side"`` marks an entry that must not become the new leaf.
    append_mode: Literal["side"] | None = None


@dataclass(frozen=True)
class MessageEntry(SessionTreeEntryBase):
    """A transcript message. Parity: ``MessageEntry``."""

    message: AgentMessage | None = None
    type: Literal["message"] = "message"


@dataclass(frozen=True)
class ThinkingLevelChangeEntry(SessionTreeEntryBase):
    """Records a thinking-level change. Parity: ``ThinkingLevelChangeEntry``.

    ``thinking_level`` is a bare ``str``, not the ``ThinkingLevel`` literal:
    a persisted session may hold a level this build no longer recognizes,
    and refusing to load it would lose the whole conversation.
    """

    thinking_level: str = ""
    type: Literal["thinking_level_change"] = "thinking_level_change"


@dataclass(frozen=True)
class ModelChangeEntry(SessionTreeEntryBase):
    """Records a model switch. Parity: ``ModelChangeEntry``.

    Provider and model id are stored separately because the same model id
    can be reached through different providers, and replay needs both.
    """

    provider: str = ""
    model_id: str = ""
    type: Literal["model_change"] = "model_change"


@dataclass(frozen=True)
class CompactionEntry(SessionTreeEntryBase):
    """Marks a compaction point. Parity: ``CompactionEntry<T>``.

    ``first_kept_entry_id`` is the load-bearing field: replay resumes from
    it rather than from the compaction entry itself, which is how
    post-compaction turns survive. See
    :func:`jarvis_agent.session_context.build_session_context`.

    ``from_hook`` records that an application hook produced the summary
    rather than the built-in summarizer.
    """

    summary: str = ""
    first_kept_entry_id: str = ""
    tokens_before: int = 0
    details: Any = None
    from_hook: bool | None = None
    type: Literal["compaction"] = "compaction"


@dataclass(frozen=True)
class BranchSummaryEntry(SessionTreeEntryBase):
    """Summary of a branch returned from. Parity: ``BranchSummaryEntry<T>``."""

    from_id: str = ""
    summary: str = ""
    details: Any = None
    from_hook: bool | None = None
    type: Literal["branch_summary"] = "branch_summary"


@dataclass(frozen=True)
class CustomEntry(SessionTreeEntryBase):
    """Application data with no model-visible content. Parity: ``CustomEntry<T>``.

    Distinct from :class:`CustomMessageEntry`: this one never enters model
    context. The payload field is ``data``, not ``content``, and that naming
    difference is the whole signal.
    """

    custom_type: str = ""
    data: Any = None
    type: Literal["custom"] = "custom"


@dataclass(frozen=True)
class CustomMessageEntry(SessionTreeEntryBase):
    """Application content that *does* enter model context.

    Parity: ``CustomMessageEntry<T>``.
    """

    custom_type: str = ""
    content: str | list[TextContent | ImageContent] = ""
    display: bool = True
    details: Any = None
    type: Literal["custom_message"] = "custom_message"


@dataclass(frozen=True)
class LabelEntry(SessionTreeEntryBase):
    """Labels another entry. Parity: ``LabelEntry``.

    ``label`` is ``str | undefined`` in the TS, where ``None`` means
    *remove* the label. Since the tree is append-only there is no other way
    to unset one, so ``None`` must not be treated as "no change".
    """

    target_id: str = ""
    label: str | None = None
    type: Literal["label"] = "label"


@dataclass(frozen=True)
class SessionInfoEntry(SessionTreeEntryBase):
    """Session-level metadata such as a name. Parity: ``SessionInfoEntry``."""

    name: str | None = None
    type: Literal["session_info"] = "session_info"


@dataclass(frozen=True)
class LeafEntry(SessionTreeEntryBase):
    """Moves the active leaf pointer. Parity: ``LeafEntry``.

    This is how switching branches is recorded without mutating anything.
    ``target_id=None`` resets to an empty conversation.
    ``append_parent_id`` overrides where the *next* append attaches, which
    is not the same as the leaf itself.
    """

    target_id: str | None = None
    append_parent_id: str | None = None
    type: Literal["leaf"] = "leaf"


#: Parity: ``SessionTreeEntry`` — the ten-variant union, in declaration order.
SessionTreeEntry: TypeAlias = Union[
    MessageEntry,
    ThinkingLevelChangeEntry,
    ModelChangeEntry,
    CompactionEntry,
    BranchSummaryEntry,
    CustomEntry,
    CustomMessageEntry,
    LabelEntry,
    SessionInfoEntry,
    LeafEntry,
]

#: Every ``SessionTreeEntry.type`` value. Not a value in the TS; needed so
#: loaders and tests enumerate the variants from one place.
SESSION_TREE_ENTRY_TYPES: tuple[str, ...] = (
    "message",
    "thinking_level_change",
    "model_change",
    "compaction",
    "branch_summary",
    "custom",
    "custom_message",
    "label",
    "session_info",
    "leaf",
)


# ─────────────────────────────────────────────────────────────────────
# Derived views
# ─────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class SessionModelRef:
    """The ``{ provider, modelId }`` pair inside ``SessionContext``.

    Inlined as an anonymous object in the TS; named here because Python has
    no anonymous object types and an untyped dict would lose the shape.
    """

    provider: str
    model_id: str


@dataclass(frozen=True)
class SessionContext:
    """Replayed state for one leaf. Parity: ``SessionContext``.

    Produced by :func:`jarvis_agent.session_context.build_session_context`.
    ``model`` is ``None`` when the session never recorded a model change and
    the caller should fall back to its configured default.
    """

    messages: list[AgentMessage] = field(default_factory=list)
    thinking_level: str = ""
    model: SessionModelRef | None = None


@dataclass(frozen=True)
class FileOperations:
    """Files touched during a run. Parity: ``FileOperations``.

    Sets, not lists: the same file read twice is one read. ``written`` and
    ``edited`` are tracked apart because creating a file and modifying an
    existing one are different facts for a summary to report.
    """

    read: set[str] = field(default_factory=set)
    written: set[str] = field(default_factory=set)
    edited: set[str] = field(default_factory=set)


@dataclass(frozen=True)
class BranchSummaryResult:
    """Parity: ``BranchSummaryResult``.

    Lists rather than sets, unlike :class:`FileOperations` — this shape is
    persisted and rendered, so a stable order matters.
    """

    summary: str = ""
    read_files: list[str] = field(default_factory=list)
    modified_files: list[str] = field(default_factory=list)


__all__ = [
    "SESSION_TREE_ENTRY_TYPES",
    "BranchSummaryEntry",
    "BranchSummaryError",
    "BranchSummaryErrorCode",
    "BranchSummaryResult",
    "CompactionEntry",
    "CompactionError",
    "CompactionErrorCode",
    "CustomEntry",
    "CustomMessageEntry",
    "Err",
    "FileOperations",
    "LabelEntry",
    "LeafEntry",
    "MessageEntry",
    "ModelChangeEntry",
    "Ok",
    "Result",
    "SessionContext",
    "SessionInfoEntry",
    "SessionModelRef",
    "SessionTreeEntry",
    "SessionTreeEntryBase",
    "ThinkingLevelChangeEntry",
    "err",
    "ok",
]
