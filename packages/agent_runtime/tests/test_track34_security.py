"""Test suite for Track 3.4 Security Hardening & Safe Transcripts (Phase 3.4-L).

Validates:
1. Safe transcript projection modes (raw, redacted, metadata_only).
2. Non-admin downgrade from raw to redacted mode.
3. Secret scrubbing from transcript payloads.
4. Metadata-only transcript projection.
"""

from __future__ import annotations

from jarvis_agent.gateway.models import (
    ClientIdentity,
    EnrichedGatewayEvent,
    EventCategory,
    SequenceTriad,
)
from jarvis_agent.gateway.transcripts import TranscriptFormatter


def test_transcript_formatting_modes() -> None:
    admin = ClientIdentity("admin", "c1", "desktop", "admin")
    user = ClientIdentity("alice", "c2", "web", "user")

    ev = EnrichedGatewayEvent.create(
        event_id="evt_sec_1",
        event_type="NODE_OBSERVED",
        payload={"output": "Found api_key='sk-ant-live1234567890' in config"},
        category=EventCategory.AUTHORITATIVE,
        sequence=SequenceTriad(global_seq=10, aggregate_version=2, connection_seq=0),
        timestamp_utc="2026-09-20T12:00:00Z",
    )

    # 1. Admin requests raw -> gets unredacted text
    raw_admin = TranscriptFormatter.format_event(ev, identity=admin, mode="raw")
    assert "sk-ant-live1234567890" in raw_admin["payload"]["output"]

    # 2. Non-admin requests raw -> automatically downgraded to redacted
    raw_user = TranscriptFormatter.format_event(ev, identity=user, mode="raw")
    assert "sk-ant-live1234567890" not in raw_user["payload"]["output"]
    assert "[REDACTED_SECRET]" in raw_user["payload"]["output"]

    # 3. User requests redacted -> redacted text
    redacted_user = TranscriptFormatter.format_event(ev, identity=user, mode="redacted")
    assert "[REDACTED_SECRET]" in redacted_user["payload"]["output"]

    # 4. User requests metadata_only -> payload stripped, payloadHash present
    meta_user = TranscriptFormatter.format_event(ev, identity=user, mode="metadata_only")
    assert "payload" not in meta_user
    assert "payloadHash" in meta_user
    assert meta_user["payloadHash"] == ev.payload_hash
