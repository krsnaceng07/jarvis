"""Workboard database and in-memory state store."""

from __future__ import annotations

import base64
import json
import sqlite3
import time
from typing import Any, Literal
import uuid

from .types import (
    WORKBOARD_STATUSES,
    WorkboardAttachment,
    WorkboardBoardMetadata,
    WorkboardCard,
    WorkboardClaim,
    WorkboardComment,
    WorkboardEvent,
    WorkboardPriority,
    WorkboardProof,
    WorkboardStatus,
)


def _now_ms() -> int:
    return int(time.time() * 1000)


class WorkboardStore:
    """SQLite-backed or in-memory Workboard persistence store."""

    def __init__(self, db_path: str = ":memory:") -> None:
        self.db_path = db_path
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        with self._conn:
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS workboard_boards (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT,
                    icon TEXT,
                    color TEXT,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL,
                    archived_at INTEGER
                )
            """)
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS workboard_cards (
                    id TEXT PRIMARY KEY,
                    board_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    status TEXT NOT NULL,
                    priority TEXT NOT NULL,
                    notes TEXT,
                    labels_json TEXT NOT NULL DEFAULT '[]',
                    agent_id TEXT,
                    session_key TEXT,
                    run_id TEXT,
                    position INTEGER NOT NULL DEFAULT 0,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL,
                    started_at INTEGER,
                    completed_at INTEGER,
                    claim_json TEXT,
                    comments_json TEXT NOT NULL DEFAULT '[]',
                    proof_json TEXT NOT NULL DEFAULT '[]',
                    events_json TEXT NOT NULL DEFAULT '[]',
                    metadata_json TEXT NOT NULL DEFAULT '{}'
                )
            """)
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS workboard_attachments (
                    id TEXT PRIMARY KEY,
                    card_id TEXT NOT NULL,
                    file_name TEXT NOT NULL,
                    byte_size INTEGER NOT NULL,
                    content_base64 TEXT NOT NULL,
                    mime_type TEXT,
                    note TEXT,
                    created_at INTEGER NOT NULL
                )
            """)
            # Ensure default board exists
            self.ensure_default_board()

    def ensure_default_board(self) -> None:
        row = self._conn.execute("SELECT id FROM workboard_boards WHERE id = 'default'").fetchone()
        if not row:
            now = _now_ms()
            self._conn.execute(
                "INSERT INTO workboard_boards (id, name, description, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                ("default", "Default Board", "Main workboard", now, now),
            )

    def list_boards(self, include_archived: bool = False) -> list[WorkboardBoardMetadata]:
        query = "SELECT * FROM workboard_boards"
        if not include_archived:
            query += " WHERE archived_at IS NULL"
        query += " ORDER BY created_at ASC"
        rows = self._conn.execute(query).fetchall()
        return [
            WorkboardBoardMetadata(
                id=r["id"],
                name=r["name"],
                description=r["description"],
                icon=r["icon"],
                color=r["color"],
                created_at=r["created_at"],
                updated_at=r["updated_at"],
                archived_at=r["archived_at"],
            )
            for r in rows
        ]

    def create_board(
        self, board_id: str, name: str, description: str | None = None
    ) -> WorkboardBoardMetadata:
        now = _now_ms()
        with self._conn:
            self._conn.execute(
                "INSERT INTO workboard_boards (id, name, description, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (board_id, name, description, now, now),
            )
        return WorkboardBoardMetadata(
            id=board_id, name=name, description=description, created_at=now, updated_at=now
        )

    def archive_board(self, board_id: str) -> bool:
        now = _now_ms()
        with self._conn:
            cur = self._conn.execute(
                "UPDATE workboard_boards SET archived_at = ?, updated_at = ? WHERE id = ?",
                (now, now, board_id),
            )
            return cur.rowcount > 0

    def delete_board(self, board_id: str) -> bool:
        with self._conn:
            cur = self._conn.execute("DELETE FROM workboard_boards WHERE id = ?", (board_id,))
            return cur.rowcount > 0

    def _row_to_card(self, r: sqlite3.Row) -> WorkboardCard:
        labels = json.loads(r["labels_json"])
        claim_dict = json.loads(r["claim_json"]) if r["claim_json"] else None
        claim = WorkboardClaim(**claim_dict) if claim_dict else None

        comments = [WorkboardComment(**c) for c in json.loads(r["comments_json"])]
        proof = [WorkboardProof(**p) for p in json.loads(r["proof_json"])]
        events = [WorkboardEvent(**e) for e in json.loads(r["events_json"])]
        meta = json.loads(r["metadata_json"])

        # Fetch attachments
        att_rows = self._conn.execute(
            "SELECT id, card_id, file_name, byte_size, mime_type, note, created_at FROM workboard_attachments WHERE card_id = ?",
            (r["id"],),
        ).fetchall()
        attachments = [
            WorkboardAttachment(
                id=a["id"],
                card_id=a["card_id"],
                file_name=a["file_name"],
                byte_size=a["byte_size"],
                created_at=a["created_at"],
                mime_type=a["mime_type"],
                note=a["note"],
            )
            for a in att_rows
        ]

        return WorkboardCard(
            id=r["id"],
            title=r["title"],
            status=r["status"],
            priority=r["priority"],
            board_id=r["board_id"],
            notes=r["notes"],
            labels=labels,
            agent_id=r["agent_id"],
            session_key=r["session_key"],
            run_id=r["run_id"],
            position=r["position"],
            created_at=r["created_at"],
            updated_at=r["updated_at"],
            started_at=r["started_at"],
            completed_at=r["completed_at"],
            claim=claim,
            comments=comments,
            proof=proof,
            attachments=attachments,
            events=events,
            metadata=meta,
        )

    def list_cards(
        self,
        board_id: str | None = None,
        status: str | None = None,
        agent_id: str | None = None,
    ) -> list[WorkboardCard]:
        query = "SELECT * FROM workboard_cards WHERE 1=1"
        params: list[Any] = []
        if board_id:
            query += " AND board_id = ?"
            params.append(board_id)
        if status:
            query += " AND status = ?"
            params.append(status)
        if agent_id:
            query += " AND agent_id = ?"
            params.append(agent_id)
        query += " ORDER BY position ASC, created_at DESC"
        rows = self._conn.execute(query, params).fetchall()
        return [self._row_to_card(r) for r in rows]

    def get_card(self, card_id: str) -> WorkboardCard | None:
        row = self._conn.execute(
            "SELECT * FROM workboard_cards WHERE id = ?", (card_id,)
        ).fetchone()
        return self._row_to_card(row) if row else None

    def create_card(
        self,
        title: str,
        board_id: str = "default",
        notes: str | None = None,
        priority: WorkboardPriority = "normal",
        status: WorkboardStatus = "todo",
        labels: list[str] | None = None,
    ) -> WorkboardCard:
        card_id = f"card-{uuid.uuid4().hex[:8]}"
        now = _now_ms()
        labels_list = labels or []
        created_event = WorkboardEvent(
            id=str(uuid.uuid4()), kind="created", at=now, to_status=status
        )
        events_json = json.dumps(
            [
                {
                    "id": created_event.id,
                    "kind": created_event.kind,
                    "at": created_event.at,
                    "to_status": status,
                }
            ]
        )

        with self._conn:
            self._conn.execute(
                """
                INSERT INTO workboard_cards (
                    id, board_id, title, status, priority, notes, labels_json, created_at, updated_at, events_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    card_id,
                    board_id,
                    title,
                    status,
                    priority,
                    notes,
                    json.dumps(labels_list),
                    now,
                    now,
                    events_json,
                ),
            )
        card = self.get_card(card_id)
        if not card:
            raise RuntimeError("Failed to retrieve created card")
        return card

    def move_card(self, card_id: str, to_status: WorkboardStatus) -> WorkboardCard | None:
        card = self.get_card(card_id)
        if not card:
            return None
        now = _now_ms()
        from_status = card.status
        ev = WorkboardEvent(
            id=str(uuid.uuid4()), kind="moved", at=now, from_status=from_status, to_status=to_status
        )
        events = list(card.events) + [ev]
        events_dicts = [
            {
                "id": e.id,
                "kind": e.kind,
                "at": e.at,
                "from_status": e.from_status,
                "to_status": e.to_status,
            }
            for e in events
        ]

        completed_at = now if to_status == "done" else card.completed_at
        started_at = now if to_status == "running" and not card.started_at else card.started_at

        with self._conn:
            self._conn.execute(
                """
                UPDATE workboard_cards SET status = ?, updated_at = ?, started_at = ?, completed_at = ?, events_json = ? WHERE id = ?
                """,
                (to_status, now, started_at, completed_at, json.dumps(events_dicts), card_id),
            )
        return self.get_card(card_id)

    def claim_card(
        self,
        card_id: str,
        owner_id: str,
        timeout_seconds: int = 300,
    ) -> tuple[bool, str | None, WorkboardCard | None]:
        card = self.get_card(card_id)
        if not card:
            return False, "Card not found", None

        now = _now_ms()
        # Check active claim
        if card.claim:
            if (
                card.claim.owner_id != owner_id
                and card.claim.expires_at
                and card.claim.expires_at > now
            ):
                return False, f"Card already claimed by {card.claim.owner_id}", card

        token = uuid.uuid4().hex
        expires_at = now + (timeout_seconds * 1000)
        claim = WorkboardClaim(
            owner_id=owner_id,
            token=token,
            claimed_at=now,
            last_heartbeat_at=now,
            expires_at=expires_at,
        )
        claim_json = json.dumps(
            {
                "owner_id": claim.owner_id,
                "token": claim.token,
                "claimed_at": claim.claimed_at,
                "last_heartbeat_at": claim.last_heartbeat_at,
                "expires_at": claim.expires_at,
            }
        )

        ev = WorkboardEvent(
            id=str(uuid.uuid4()),
            kind="claimed",
            at=now,
            from_status=card.status,
            to_status="running",
        )
        events = list(card.events) + [ev]
        events_dicts = [
            {
                "id": e.id,
                "kind": e.kind,
                "at": e.at,
                "from_status": e.from_status,
                "to_status": e.to_status,
            }
            for e in events
        ]

        with self._conn:
            self._conn.execute(
                """
                UPDATE workboard_cards SET status = 'running', claim_json = ?, started_at = COALESCE(started_at, ?), updated_at = ?, events_json = ? WHERE id = ?
                """,
                (claim_json, now, now, json.dumps(events_dicts), card_id),
            )
        return True, token, self.get_card(card_id)

    def heartbeat_card(
        self, card_id: str, owner_id: str, token: str, timeout_seconds: int = 300
    ) -> bool:
        card = self.get_card(card_id)
        if not card or not card.claim:
            return False
        if card.claim.owner_id != owner_id or card.claim.token != token:
            return False

        now = _now_ms()
        expires_at = now + (timeout_seconds * 1000)
        claim = WorkboardClaim(
            owner_id=owner_id,
            token=token,
            claimed_at=card.claim.claimed_at,
            last_heartbeat_at=now,
            expires_at=expires_at,
        )
        claim_json = json.dumps(
            {
                "owner_id": claim.owner_id,
                "token": claim.token,
                "claimed_at": claim.claimed_at,
                "last_heartbeat_at": claim.last_heartbeat_at,
                "expires_at": claim.expires_at,
            }
        )
        with self._conn:
            self._conn.execute(
                "UPDATE workboard_cards SET claim_json = ?, updated_at = ? WHERE id = ?",
                (claim_json, now, card_id),
            )
        return True

    def complete_card(self, card_id: str, owner_id: str, token: str) -> bool:
        card = self.get_card(card_id)
        if not card or not card.claim:
            return False
        if card.claim.owner_id != owner_id or card.claim.token != token:
            return False

        now = _now_ms()
        ev = WorkboardEvent(
            id=str(uuid.uuid4()),
            kind="execution_updated",
            at=now,
            from_status=card.status,
            to_status="done",
        )
        events = list(card.events) + [ev]
        events_dicts = [
            {
                "id": e.id,
                "kind": e.kind,
                "at": e.at,
                "from_status": e.from_status,
                "to_status": e.to_status,
            }
            for e in events
        ]

        with self._conn:
            self._conn.execute(
                """
                UPDATE workboard_cards SET status = 'done', claim_json = NULL, completed_at = ?, updated_at = ?, events_json = ? WHERE id = ?
                """,
                (now, now, json.dumps(events_dicts), card_id),
            )
        return True

    def block_card(self, card_id: str, reason: str) -> WorkboardCard | None:
        card = self.get_card(card_id)
        if not card:
            return None
        now = _now_ms()
        ev = WorkboardEvent(
            id=str(uuid.uuid4()),
            kind="diagnostic",
            at=now,
            from_status=card.status,
            to_status="blocked",
        )
        events = list(card.events) + [ev]
        events_dicts = [
            {
                "id": e.id,
                "kind": e.kind,
                "at": e.at,
                "from_status": e.from_status,
                "to_status": e.to_status,
            }
            for e in events
        ]

        meta = dict(card.metadata)
        meta["blockReason"] = reason

        with self._conn:
            self._conn.execute(
                """
                UPDATE workboard_cards SET status = 'blocked', updated_at = ?, metadata_json = ?, events_json = ? WHERE id = ?
                """,
                (now, json.dumps(meta), json.dumps(events_dicts), card_id),
            )
        return self.get_card(card_id)

    def unblock_card(self, card_id: str) -> WorkboardCard | None:
        card = self.get_card(card_id)
        if not card:
            return None
        now = _now_ms()
        ev = WorkboardEvent(
            id=str(uuid.uuid4()),
            kind="diagnostic",
            at=now,
            from_status="blocked",
            to_status="ready",
        )
        events = list(card.events) + [ev]
        events_dicts = [
            {
                "id": e.id,
                "kind": e.kind,
                "at": e.at,
                "from_status": e.from_status,
                "to_status": e.to_status,
            }
            for e in events
        ]

        meta = dict(card.metadata)
        meta.pop("blockReason", None)

        with self._conn:
            self._conn.execute(
                """
                UPDATE workboard_cards SET status = 'ready', updated_at = ?, metadata_json = ?, events_json = ? WHERE id = ?
                """,
                (now, json.dumps(meta), json.dumps(events_dicts), card_id),
            )
        return self.get_card(card_id)

    def add_comment(self, card_id: str, body: str) -> WorkboardComment:
        card = self.get_card(card_id)
        if not card:
            raise KeyError(f"Card not found: {card_id}")
        now = _now_ms()
        comment = WorkboardComment(id=str(uuid.uuid4()), body=body, created_at=now)
        comments = list(card.comments) + [comment]
        comments_json = json.dumps(
            [
                {"id": c.id, "body": c.body, "created_at": c.created_at, "updated_at": c.updated_at}
                for c in comments
            ]
        )

        with self._conn:
            self._conn.execute(
                "UPDATE workboard_cards SET comments_json = ?, updated_at = ? WHERE id = ?",
                (comments_json, now, card_id),
            )
        return comment

    def add_proof(
        self,
        card_id: str,
        status: Literal["passed", "failed", "skipped", "unknown"],
        label: str | None = None,
        command: str | None = None,
        url: str | None = None,
        note: str | None = None,
    ) -> WorkboardProof:
        card = self.get_card(card_id)
        if not card:
            raise KeyError(f"Card not found: {card_id}")
        now = _now_ms()
        p = WorkboardProof(
            id=str(uuid.uuid4()),
            status=status,
            created_at=now,
            label=label,
            command=command,
            url=url,
            note=note,
        )
        proofs = list(card.proof) + [p]
        proofs_json = json.dumps(
            [
                {
                    "id": item.id,
                    "status": item.status,
                    "created_at": item.created_at,
                    "label": item.label,
                    "command": item.command,
                    "url": item.url,
                    "note": item.note,
                }
                for item in proofs
            ]
        )

        with self._conn:
            self._conn.execute(
                "UPDATE workboard_cards SET proof_json = ?, updated_at = ? WHERE id = ?",
                (proofs_json, now, card_id),
            )
        return p

    def add_attachment(
        self,
        card_id: str,
        file_name: str,
        content: bytes,
        mime_type: str | None = None,
        note: str | None = None,
    ) -> WorkboardAttachment:
        card = self.get_card(card_id)
        if not card:
            raise KeyError(f"Card not found: {card_id}")
        now = _now_ms()
        att_id = f"att-{uuid.uuid4().hex[:8]}"
        b64_content = base64.b64encode(content).decode("ascii")

        with self._conn:
            self._conn.execute(
                """
                INSERT INTO workboard_attachments (
                    id, card_id, file_name, byte_size, content_base64, mime_type, note, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (att_id, card_id, file_name, len(content), b64_content, mime_type, note, now),
            )
        return WorkboardAttachment(
            id=att_id,
            card_id=card_id,
            file_name=file_name,
            byte_size=len(content),
            created_at=now,
            mime_type=mime_type,
            note=note,
        )

    def read_attachment(self, attachment_id: str) -> tuple[WorkboardAttachment, bytes] | None:
        row = self._conn.execute(
            "SELECT * FROM workboard_attachments WHERE id = ?", (attachment_id,)
        ).fetchone()
        if not row:
            return None
        att = WorkboardAttachment(
            id=row["id"],
            card_id=row["card_id"],
            file_name=row["file_name"],
            byte_size=row["byte_size"],
            created_at=row["created_at"],
            mime_type=row["mime_type"],
            note=row["note"],
        )
        content = base64.b64decode(row["content_base64"])
        return att, content

    def delete_attachment(self, attachment_id: str) -> bool:
        with self._conn:
            cur = self._conn.execute(
                "DELETE FROM workboard_attachments WHERE id = ?", (attachment_id,)
            )
            return cur.rowcount > 0

    def get_stats(self, board_id: str | None = None) -> dict[str, Any]:
        cards = self.list_cards(board_id=board_id)
        by_status: dict[str, int] = {s: 0 for s in WORKBOARD_STATUSES}
        for c in cards:
            by_status[c.status] = by_status.get(c.status, 0) + 1

        active = sum(by_status[s] for s in WORKBOARD_STATUSES if s != "done")
        return {
            "total": len(cards),
            "active": active,
            "done": by_status.get("done", 0),
            "byStatus": by_status,
        }
