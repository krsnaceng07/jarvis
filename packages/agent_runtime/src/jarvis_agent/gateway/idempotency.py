"""Durable request idempotency ledger for Track 3.4.

Enforces Invariant T34-13: Mutating gateway requests carry durable request IDs
and reject same-ID/different-payload reuse with REQUEST_CONFLICT.
"""

from __future__ import annotations

from dataclasses import dataclass
import datetime
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any

from jarvis_agent.gateway.errors import GatewayErrorCode, GatewayException


@dataclass(frozen=True, slots=True)
class GatewayRequestRecord:
    """Stored request entry in the idempotency ledger."""

    request_id: str
    client_identity_id: str
    session_id: str
    method: str
    payload_hash: str
    status: str  # "PENDING", "COMPLETED", "FAILED"
    response_payload: Any | None
    created_at_utc: str
    updated_at_utc: str


class GatewayRequestLedger:
    """SQLite WAL durable ledger preventing duplicate execution of mutating requests."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = str(db_path or ":memory:")
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        with self._conn:
            self._conn.execute("PRAGMA journal_mode = WAL;")
            self._conn.execute("PRAGMA synchronous = NORMAL;")
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS gateway_requests (
                    request_id TEXT PRIMARY KEY,
                    client_identity_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    method TEXT NOT NULL,
                    payload_hash TEXT NOT NULL,
                    status TEXT NOT NULL,
                    response_payload TEXT,
                    created_at_utc TEXT NOT NULL,
                    updated_at_utc TEXT NOT NULL
                );
                """
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_gw_req_sess ON gateway_requests(session_id);"
            )

    def close(self) -> None:
        """Close SQLite database connection safely."""
        try:
            self._conn.close()
        except Exception:
            pass

    @staticmethod
    def hash_payload(payload: Any) -> str:
        """Compute canonical SHA-256 hash of payload."""
        serialized = json.dumps(payload, sort_keys=True, default=str)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def check_or_record(
        self,
        request_id: str,
        client_identity_id: str,
        session_id: str,
        method: str,
        payload: Any,
    ) -> tuple[bool, Any | None]:
        """Check request idempotency; returns (is_new, cached_response).

        Raises:
            GatewayException(REQUEST_CONFLICT) if same request_id used with differing payload.
            GatewayException(REQUEST_DUPLICATE) if request is currently PENDING in flight.
        """
        if not request_id:
            # Non-idempotent untracked call
            return True, None

        payload_hash = self.hash_payload(payload)
        now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()

        with self._conn:
            cur = self._conn.execute(
                "SELECT * FROM gateway_requests WHERE request_id = ?", (request_id,)
            )
            row = cur.fetchone()

            if row:
                stored_hash = row["payload_hash"]
                stored_status = row["status"]
                stored_resp = row["response_payload"]

                if stored_hash != payload_hash:
                    raise GatewayException(
                        code=GatewayErrorCode.REQUEST_CONFLICT,
                        message=f"Request ID '{request_id}' reused with conflicting payload.",
                        data={"request_id": request_id, "method": method},
                    )

                if stored_status == "PENDING":
                    raise GatewayException(
                        code=GatewayErrorCode.REQUEST_DUPLICATE,
                        message=f"Request '{request_id}' is already in flight.",
                        data={"request_id": request_id},
                    )

                parsed_resp = json.loads(stored_resp) if stored_resp else None
                return False, parsed_resp

            # Insert new PENDING request
            self._conn.execute(
                """
                INSERT INTO gateway_requests (
                    request_id, client_identity_id, session_id, method, payload_hash,
                    status, response_payload, created_at_utc, updated_at_utc
                ) VALUES (?, ?, ?, ?, ?, 'PENDING', NULL, ?, ?);
                """,
                (
                    request_id,
                    client_identity_id,
                    session_id,
                    method,
                    payload_hash,
                    now_str,
                    now_str,
                ),
            )
            return True, None

    def complete_request(self, request_id: str, response_payload: Any) -> None:
        """Mark request as COMPLETED and cache its response payload."""
        if not request_id:
            return
        now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()
        serialized = json.dumps(response_payload, default=str)
        with self._conn:
            self._conn.execute(
                """
                UPDATE gateway_requests
                SET status = 'COMPLETED', response_payload = ?, updated_at_utc = ?
                WHERE request_id = ?;
                """,
                (serialized, now_str, request_id),
            )

    def fail_request(self, request_id: str, error_payload: Any) -> None:
        """Mark request as FAILED."""
        if not request_id:
            return
        now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()
        serialized = json.dumps(error_payload, default=str)
        with self._conn:
            self._conn.execute(
                """
                UPDATE gateway_requests
                SET status = 'FAILED', response_payload = ?, updated_at_utc = ?
                WHERE request_id = ?;
                """,
                (serialized, now_str, request_id),
            )


__all__ = ["GatewayRequestRecord", "GatewayRequestLedger"]
