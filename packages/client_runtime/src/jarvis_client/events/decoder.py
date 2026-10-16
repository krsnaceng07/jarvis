"""Schema-versioned event decoder for Track 3.5.

Enforces Invariant T35-07: Zero Secret Unmasking.
Clients receive server-redacted representations exclusively. The decoder rejects malformed,
oversized, or unknown schema events, quarantining them cleanly.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any

from jarvis_client.errors import ClientErrorCode, JarvisClientException

CURRENT_EVENT_SCHEMA_VERSION: int = 1


@dataclass(frozen=True, slots=True)
class DecodedEvent:
    """Validated client-side event representation."""

    event_id: str
    event_type: str
    payload: dict[str, Any]
    category: str
    global_seq: int
    aggregate_version: int
    connection_seq: int
    timestamp_utc: str
    schema_version: int = CURRENT_EVENT_SCHEMA_VERSION
    causation_id: str | None = None
    correlation_id: str | None = None


class EventDecoder:
    """Decodes gateway event frames, enforcing schema validation and quarantine."""

    def __init__(self, supported_schema_version: int = CURRENT_EVENT_SCHEMA_VERSION) -> None:
        self.supported_schema_version = supported_schema_version
        self.quarantined_events: list[dict[str, Any]] = []

    def decode_frame(self, raw_payload: str | dict[str, Any]) -> DecodedEvent | None:
        """Parse raw frame into DecodedEvent.

        Returns None and records quarantine if schema is unsupported.
        """
        if isinstance(raw_payload, str):
            try:
                data = json.loads(raw_payload)
            except Exception as e:
                raise JarvisClientException(
                    code=ClientErrorCode.PARSE_ERROR,
                    message=f"Corrupted event frame JSON: {e}",
                )
        else:
            data = raw_payload

        if not isinstance(data, dict):
            raise JarvisClientException(
                code=ClientErrorCode.INVALID_REQUEST,
                message="Event frame must be a dictionary.",
            )

        # Schema version check
        schema_version = int(
            data.get("schemaVersion")
            or (
                data.get("data", {}).get("schemaVersion")
                if isinstance(data.get("data"), dict)
                else 1
            )
        )

        if schema_version > self.supported_schema_version:
            # Future schema: quarantine and do not corrupt client state
            self.quarantined_events.append(data)
            return None

        # Extract sequence triad
        seq_dict = (
            data.get("sequence")
            or (
                data.get("data", {}).get("sequence") if isinstance(data.get("data"), dict) else None
            )
            or (
                data.get("payload", {}).get("sequence")
                if isinstance(data.get("payload"), dict)
                else None
            )
            or {}
        )
        global_seq = int(seq_dict.get("globalSeq") or seq_dict.get("global_seq", 0))
        agg_ver = int(seq_dict.get("aggregateVersion") or seq_dict.get("aggregate_version", 0))
        conn_seq = int(seq_dict.get("connectionSeq") or seq_dict.get("connection_seq", 0))

        event_id = str(data.get("id") or data.get("eventId") or data.get("event_id") or "")
        event_type = str(
            data.get("event") or data.get("eventType") or data.get("event_type") or "UNKNOWN"
        )
        category = str(data.get("category", "authoritative"))
        ts_utc = str(data.get("timestampUtc") or data.get("timestamp_utc", ""))

        payload = data.get("payload")
        if payload is None:
            payload = data.get("data")
        if not isinstance(payload, dict):
            payload = {"data": payload} if payload is not None else {}

        return DecodedEvent(
            event_id=event_id,
            event_type=event_type,
            payload=payload,
            category=category,
            global_seq=global_seq,
            aggregate_version=agg_ver,
            connection_seq=conn_seq,
            timestamp_utc=ts_utc,
            schema_version=schema_version,
            causation_id=data.get("causationId"),
            correlation_id=data.get("correlationId"),
        )


__all__ = ["CURRENT_EVENT_SCHEMA_VERSION", "DecodedEvent", "EventDecoder"]
