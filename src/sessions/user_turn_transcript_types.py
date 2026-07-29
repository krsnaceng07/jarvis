"""User-turn transcript type contracts shared by runtime and queue option types.

Mirrors OpenClaw's ``src/sessions/user-turn-transcript.types.ts``.

Type-only module: the port keeps the same shape as the TS
source for the contracts the recorder helpers depend on.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable, Literal, Optional, TypedDict, Union

from src.sessions.input_provenance import InputProvenance

# Public literal unions + closed-set membership constants.
UserTurnTranscriptUpdateMode = Literal["inline", "none"]
VALID_USER_TURN_TRANSCRIPT_UPDATE_MODES: frozenset[str] = frozenset({"inline", "none"})


class PersistedUserTurnMediaInput(TypedDict, total=False):
    path: Optional[str]
    url: Optional[str]
    contentType: Optional[str]
    kind: Optional[str]


class UserTurnSender(TypedDict, total=False):
    id: Optional[str]
    name: Optional[str]
    username: Optional[str]


class UserTurnTransport(TypedDict, total=False):
    channel: str
    conversationRef: str
    messageId: str
    replyToId: str
    threadId: str


class UserTurnInput(TypedDict, total=False):
    text: Optional[str]
    media: Optional[list[PersistedUserTurnMediaInput]]
    timestamp: int
    idempotencyKey: str
    senderIsOwner: bool
    provenance: InputProvenance
    sender: Optional[UserTurnSender]
    transport: UserTurnTransport


class UserTurnSessionEntry(TypedDict, total=False):
    sessionId: str
    updatedAt: int
    sessionFile: str
    threadId: Optional[Union[str, int]]


# Minimal AgentMessage shape; matches ``Extract<AgentMessage, { role: "user" }>``
# in OpenClaw. The recorder helpers do not depend on the full contract.
class PersistedUserTurnMessage(TypedDict, total=False):
    role: str
    content: Any
    text: str


# Lifecycle patch / expected state contracts reused by the
# recorder. They are referenced by name in
# PersistUserTurnTranscriptParams and
# CreateUserTurnTranscriptRecorderParams; the port keeps them
# as TypedDicts for type hints only.
class SessionTranscriptTurnExpectedState(TypedDict, total=False):
    # Mirrors the OpenClaw lifecycle turn-expected-state shape.
    expectedStatus: str
    expectedGeneration: int
    expectedSessionId: str


class SessionTranscriptTurnLifecyclePatch(TypedDict, total=False):
    status: str
    generation: int
    sessionId: str
    threadId: Optional[Union[str, int]]


class UserTurnBeforeMessageWriteParams(TypedDict, total=False):
    message: PersistedUserTurnMessage
    agentId: str
    sessionKey: str


UserTurnBeforeMessageWrite = Callable[
    [UserTurnBeforeMessageWriteParams], Optional[PersistedUserTurnMessage]
]


class UserTurnMessagePersistenceParams(TypedDict, total=False):
    input: UserTurnInput
    message: PersistedUserTurnMessage
    sessionId: str
    agentId: str
    sessionKey: str
    cwd: str
    config: Any
    updateMode: UserTurnTranscriptUpdateMode
    beforeMessageWrite: UserTurnBeforeMessageWrite


class UserTurnTranscriptTarget(TypedDict, total=False):
    sessionId: str
    expectedSessionId: str
    sessionKey: str
    sessionEntry: Optional[UserTurnSessionEntry]
    sessionStore: dict[str, UserTurnSessionEntry]
    storePath: str
    agentId: str
    threadId: Optional[Union[str, int]]
    cwd: str
    config: Any
    beforeMessageWrite: UserTurnBeforeMessageWrite


class UserTurnTranscriptPersistResult(TypedDict, total=False):
    appended: bool
    sessionFile: str
    sessionEntry: Optional[UserTurnSessionEntry]
    messageId: str
    message: PersistedUserTurnMessage


UserTurnTranscriptTargetResolver = Union[
    UserTurnTranscriptTarget,
    Callable[[], Union[UserTurnTranscriptTarget, None, Awaitable[Optional[UserTurnTranscriptTarget]]]],
]


class PersistUserTurnTranscriptParams(TypedDict, total=False):
    input: UserTurnInput
    message: PersistedUserTurnMessage
    sessionId: str
    expectedSessionId: str
    sessionKey: str
    sessionEntry: Optional[UserTurnSessionEntry]
    sessionStore: dict[str, UserTurnSessionEntry]
    storePath: str
    agentId: str
    threadId: Optional[Union[str, int]]
    cwd: str
    config: Any
    updateMode: UserTurnTranscriptUpdateMode
    beforeMessageWrite: UserTurnBeforeMessageWrite
    expectedSessionState: SessionTranscriptTurnExpectedState
    sessionLifecyclePatch: SessionTranscriptTurnLifecyclePatch


UserTurnInputResolver = Callable[[], Union[UserTurnInput, None, Awaitable[Optional[UserTurnInput]]]]


class CreateUserTurnTranscriptRecorderParams(TypedDict, total=False):
    input: UserTurnInput
    message: PersistedUserTurnMessage
    resolveInput: UserTurnInputResolver
    target: UserTurnTranscriptTargetResolver
    updateMode: UserTurnTranscriptUpdateMode
    beforeMessageWrite: UserTurnBeforeMessageWrite
    errorContext: str
    onPersistenceError: Callable[[Any], None]
    onMessagePersisted: Callable[[PersistedUserTurnMessage], Union[None, Awaitable[None]]]
    expectedSessionState: SessionTranscriptTurnExpectedState
    sessionLifecyclePatch: SessionTranscriptTurnLifecyclePatch


class PersistApprovedParams(TypedDict, total=False):
    target: UserTurnTranscriptTargetResolver
    updateMode: UserTurnTranscriptUpdateMode
    cwd: str
    expectedSessionId: str
    expectedSessionState: SessionTranscriptTurnExpectedState
    sessionLifecyclePatch: SessionTranscriptTurnLifecyclePatch


class PersistBlockedParams(TypedDict, total=False):
    target: UserTurnTranscriptTargetResolver
    updateMode: UserTurnTranscriptUpdateMode
    cwd: str


class PersistFallbackParams(TypedDict, total=False):
    target: UserTurnTranscriptTargetResolver
    updateMode: UserTurnTranscriptUpdateMode
    cwd: str


class UserTurnTranscriptRecorder(TypedDict, total=False):
    message: Optional[PersistedUserTurnMessage]
    resolveMessage: Callable[[], Awaitable[Optional[PersistedUserTurnMessage]]]
    getPersistedMessage: Callable[[], Optional[PersistedUserTurnMessage]]
    markSentToProvider: Callable[[], None]
    markRuntimePersistencePending: Callable[[Awaitable[None]], None]
    markRuntimePersisted: Callable[[Optional[PersistedUserTurnMessage]], None]
    markBlocked: Callable[[], None]
    hasPersisted: Callable[[], bool]
    isBlocked: Callable[[], bool]
    hasRuntimePersistencePending: Callable[[], bool]
    waitForRuntimePersistence: Callable[[], Awaitable[None]]
    persistApproved: Callable[
        [Optional[PersistApprovedParams]],
        Awaitable[Optional[UserTurnTranscriptPersistResult]],
    ]
    persistBlocked: Callable[
        [PersistedUserTurnMessage, Optional[PersistBlockedParams]],
        Awaitable[Optional[UserTurnTranscriptPersistResult]],
    ]
    persistFallback: Callable[
        [Optional[PersistFallbackParams]],
        Awaitable[Optional[UserTurnTranscriptPersistResult]],
    ]


__all__ = [
    "CreateUserTurnTranscriptRecorderParams",
    "PersistApprovedParams",
    "PersistBlockedParams",
    "PersistFallbackParams",
    "PersistUserTurnTranscriptParams",
    "PersistedUserTurnMediaInput",
    "PersistedUserTurnMessage",
    "SessionTranscriptTurnExpectedState",
    "SessionTranscriptTurnLifecyclePatch",
    "UserTurnBeforeMessageWrite",
    "UserTurnBeforeMessageWriteParams",
    "UserTurnInput",
    "UserTurnInputResolver",
    "UserTurnMessagePersistenceParams",
    "UserTurnSender",
    "UserTurnSessionEntry",
    "UserTurnTranscriptPersistResult",
    "UserTurnTranscriptRecorder",
    "UserTurnTranscriptTarget",
    "UserTurnTranscriptTargetResolver",
    "UserTurnTranscriptUpdateMode",
    "UserTurnTransport",
    "VALID_USER_TURN_TRANSCRIPT_UPDATE_MODES",
]
