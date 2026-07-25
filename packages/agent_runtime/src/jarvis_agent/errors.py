"""jarvis_agent.errors — agent-core error types.

OpenClaw parity: ``packages/agent-core/src/errors.ts``.
"""

from __future__ import annotations

#: Stable machine-readable code. Parity:
#: ``TRANSCRIPT_NOT_CONTINUABLE_ERROR_CODE``. The string keeps OpenClaw's
#: ``openclaw_`` prefix deliberately: it is a wire value that appears in
#: persisted sessions, so renaming it to ``jarvis_`` would make existing
#: transcripts unreadable by either implementation.
TRANSCRIPT_NOT_CONTINUABLE_ERROR_CODE = "openclaw_transcript_not_continuable"


class TranscriptNotContinuableError(Exception):
    """Raised when a run is resumed from a message that cannot be continued.

    Parity: ``TranscriptNotContinuableError``. Only ``assistant`` and
    ``toolResult`` tails are continuable; resuming from anything else
    would ask the provider to extend a message it did not write.

    Unlike most failures in this port, this one *is* raised rather than
    encoded in a stream: it is a caller error detected before any provider
    request starts, so there is no stream to encode it into yet.
    """

    #: Parity: the readonly ``code`` field.
    code = TRANSCRIPT_NOT_CONTINUABLE_ERROR_CODE

    def __init__(self, role: str) -> None:
        super().__init__(f"Cannot continue from message role: {role}")
        #: The offending message role, kept for callers that branch on it.
        self.role = role
        #: Parity: ``this.name = "TranscriptNotContinuableError"``.
        self.name = "TranscriptNotContinuableError"


__all__ = [
    "TRANSCRIPT_NOT_CONTINUABLE_ERROR_CODE",
    "TranscriptNotContinuableError",
]
