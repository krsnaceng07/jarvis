"""Safe transcript formatting and redaction policy for Track 3.4.

Enforces Invariant T34-21: Transcripts are projected according to caller authorization;
unauthorized callers or guest clients receive metadata-only or redacted views.
"""

from __future__ import annotations

from typing import Any

from jarvis_agent.gateway.models import ClientIdentity, EnrichedGatewayEvent
from jarvis_agent.gateway.redactor import redact_sensitive_text


class TranscriptFormatter:
    """Formats event journals into secure, policy-compliant client transcripts."""

    @staticmethod
    def format_event(
        event: EnrichedGatewayEvent,
        identity: ClientIdentity,
        mode: str = "redacted",
    ) -> dict[str, Any]:
        """Format an enriched domain event for client consumption based on policy."""
        # Non-admins cannot request raw mode
        effective_mode = mode
        if effective_mode == "raw" and identity.auth_tier != "admin":
            effective_mode = "redacted"

        base: dict[str, Any] = {
            "eventId": event.event_id,
            "eventType": event.event_type,
            "globalSeq": event.sequence.global_seq,
            "stateVersion": event.sequence.aggregate_version,
            "timestampUtc": event.timestamp_utc,
            "category": event.category.value,
        }

        if effective_mode == "metadata_only":
            base["payloadHash"] = event.payload_hash
            return base

        payload = event.payload
        if effective_mode == "redacted" and isinstance(payload, dict):
            scrubbed: dict[str, Any] = {}
            for k, v in payload.items():
                if isinstance(v, str):
                    scrubbed[k] = redact_sensitive_text(v)
                elif isinstance(v, dict):
                    scrubbed[k] = {
                        sub_k: redact_sensitive_text(str(sub_v))
                        if isinstance(sub_v, str)
                        else sub_v
                        for sub_k, sub_v in v.items()
                    }
                else:
                    scrubbed[k] = v
            base["payload"] = scrubbed
        else:
            base["payload"] = payload

        return base

    @classmethod
    def format_transcript(
        cls,
        events: list[EnrichedGatewayEvent],
        identity: ClientIdentity,
        mode: str = "redacted",
    ) -> list[dict[str, Any]]:
        return [cls.format_event(e, identity, mode) for e in events]


__all__ = ["TranscriptFormatter"]
