from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from jarvis_state_core.database import StateDatabase

# 1 hour in ms
PAIRING_CODE_EXPIRY_MS = 60 * 60 * 1000
# Max pending requests per channel/account
MAX_PENDING_REQUESTS = 3


def _generate_code() -> str:
    """Generate an 8-char uppercase code without ambiguous chars (0O1I)."""
    chars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(random.choices(chars, k=8))


@dataclass
class PairingRequest:
    channel: str
    account_id: str
    sender_id: str
    pairing_code: str
    created_at: int
    expires_at: int


class PairingStore:
    """Manages the pairing queue and approved senders in the state DB."""

    def __init__(self, db: StateDatabase) -> None:
        self.db = db

    def is_approved(self, channel: str, account_id: str, sender_id: str) -> bool:
        """Check if a sender is explicitly approved for a channel account."""
        with self.db.open() as conn:
            row = conn.execute(
                """
                SELECT 1 FROM channel_pairing_allow_entries
                WHERE channel = ? AND account_id = ? AND sender_id = ?
                """,
                (channel, account_id, sender_id),
            ).fetchone()
            return row is not None

    def request_pairing(
        self, channel: str, account_id: str, sender_id: str
    ) -> Optional[str]:
        """Create a new pairing request if under the limit, returning the code.

        If a valid request already exists for this sender, returns that code.
        If the queue is full for this channel/account (max 3), returns None.
        """
        now = int(time.time() * 1000)
        
        with self.db.open() as conn:
            # First clean up expired requests for this channel/account
            conn.execute(
                "DELETE FROM channel_pairing_requests WHERE channel = ? AND account_id = ? AND expires_at <= ?",
                (channel, account_id, now),
            )
            
            # Check if this sender already has a pending request
            existing = conn.execute(
                """
                SELECT pairing_code FROM channel_pairing_requests
                WHERE channel = ? AND account_id = ? AND sender_id = ?
                """,
                (channel, account_id, sender_id),
            ).fetchone()
            
            if existing:
                conn.commit()
                return existing[0]

            # Check queue limit
            count = conn.execute(
                "SELECT COUNT(*) FROM channel_pairing_requests WHERE channel = ? AND account_id = ?",
                (channel, account_id),
            ).fetchone()[0]

            if count >= MAX_PENDING_REQUESTS:
                conn.commit()
                return None

            # Create new request
            code = _generate_code()
            expires_at = now + PAIRING_CODE_EXPIRY_MS
            conn.execute(
                """
                INSERT INTO channel_pairing_requests
                (channel, account_id, sender_id, pairing_code, created_at, expires_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (channel, account_id, sender_id, code, now, expires_at),
            )
            conn.commit()
            return code

    def list_requests(self, channel: Optional[str] = None) -> list[PairingRequest]:
        """List all pending unexpired requests, optionally filtered by channel."""
        now = int(time.time() * 1000)
        with self.db.open() as conn:
            # cleanup
            conn.execute("DELETE FROM channel_pairing_requests WHERE expires_at <= ?", (now,))
            conn.commit()
            
            sql = "SELECT channel, account_id, sender_id, pairing_code, created_at, expires_at FROM channel_pairing_requests"
            params = []
            if channel:
                sql += " WHERE channel = ?"
                params.append(channel)
                
            rows = conn.execute(sql, params).fetchall()
            return [
                PairingRequest(
                    channel=r["channel"],
                    account_id=r["account_id"],
                    sender_id=r["sender_id"],
                    pairing_code=r["pairing_code"],
                    created_at=r["created_at"],
                    expires_at=r["expires_at"],
                )
                for r in rows
            ]

    def approve_code(self, channel: str, code: str) -> Optional[dict[str, str]]:
        """Approve a specific code. Returns the sender info if successful, else None."""
        now = int(time.time() * 1000)
        with self.db.open() as conn:
            # find request
            row = conn.execute(
                "SELECT account_id, sender_id FROM channel_pairing_requests WHERE channel = ? AND pairing_code = ? AND expires_at > ?",
                (channel, code, now)
            ).fetchone()
            
            if not row:
                return None
                
            account_id = row["account_id"]
            sender_id = row["sender_id"]
            
            # remove from requests
            conn.execute(
                "DELETE FROM channel_pairing_requests WHERE channel = ? AND pairing_code = ?",
                (channel, code)
            )
            
            # insert into approved
            conn.execute(
                """
                INSERT OR REPLACE INTO channel_pairing_allow_entries
                (channel, account_id, sender_id, approved_at)
                VALUES (?, ?, ?, ?)
                """,
                (channel, account_id, sender_id, now)
            )
            conn.commit()
            return {"account_id": account_id, "sender_id": sender_id}
