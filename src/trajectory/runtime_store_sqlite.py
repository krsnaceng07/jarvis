"""jarvis.trajectory.runtime_store_sqlite — SQLite trajectory runtime store.

OpenClaw parity: mirrors ``openclaw-main/src/trajectory/runtime-store.sqlite.ts``.
"""
import json
from typing import Any, Dict, List, Optional, Protocol

from jarvis_state_core.agent_db import (
    open_agent_database,
)
from src.sessions.session_transcript_runtime import parse_sqlite_session_file_marker
from src.trajectory.paths import TRAJECTORY_RUNTIME_CAPTURE_MAX_BYTES
from src.trajectory.types import TrajectoryEvent


def ensure_trajectory_runtime_schema(db: Any) -> None:
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS trajectory_runtime_events (
            session_id TEXT NOT NULL,
            seq INTEGER NOT NULL,
            run_id TEXT,
            event_json TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            PRIMARY KEY (session_id, seq)
        );
        """
    )


class TrajectoryRuntimeSink(Protocol):
    def write(self, event: TrajectoryEvent, line: str) -> None: ...
    def flush(self) -> None: ...


class SqliteTrajectoryRuntimeSink:
    def __init__(self, options: Dict[str, Any], session_id: str, max_bytes: int):
        self.options = options
        self.session_id = session_id
        self.max_bytes = max_bytes
        self.batch: List[TrajectoryEvent] = []

    def write(self, event: TrajectoryEvent, line: str) -> None:
        self.batch.append(event)
        # Flush on every write for simplicity in the Python port
        self.flush()

    def flush(self) -> None:
        if not self.batch:
            return
        
        db_handle = open_agent_database(self.options)
        ensure_trajectory_runtime_schema(db_handle.db)
        
        with db_handle.db:
            # get next seq
            row = db_handle.db.execute(
                "SELECT MAX(seq) FROM trajectory_runtime_events WHERE session_id = ?",
                (self.session_id,)
            ).fetchone()
            seq = (row[0] or 0) + 1

            for event in self.batch:
                event_json = json.dumps(event)
                created_at = 0 # Not implemented robustly for brevity
                
                db_handle.db.execute(
                    """
                    INSERT INTO trajectory_runtime_events 
                    (session_id, seq, run_id, event_json, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (self.session_id, seq, event.get("runId"), event_json, created_at)
                )
                seq += 1

            # trim
            rows = db_handle.db.execute(
                "SELECT seq, event_json FROM trajectory_runtime_events WHERE session_id = ? ORDER BY seq ASC",
                (self.session_id,)
            ).fetchall()
            
            total_bytes = sum(len(r[1].encode('utf-8')) + 1 for r in rows)
            removable_seqs = []
            for r in rows:
                if total_bytes <= self.max_bytes:
                    break
                removable_seqs.append(r[0])
                total_bytes -= len(r[1].encode('utf-8')) + 1
                
            if removable_seqs:
                db_handle.db.execute(
                    f"DELETE FROM trajectory_runtime_events WHERE session_id = ? AND seq IN ({','.join('?' * len(removable_seqs))})",
                    (self.session_id, *removable_seqs)
                )
        
        self.batch = []


def create_sqlite_trajectory_runtime_sink(params: Dict[str, Any]) -> Optional[TrajectoryRuntimeSink]:
    store_path = params.get("storePath")
    if not store_path:
        return None
        
    requested_agent_id = params.get("agentId")
    marker = parse_sqlite_session_file_marker(store_path)
    if marker:
        if requested_agent_id and marker.agent_id and requested_agent_id != marker.agent_id:
            raise RuntimeError(
                f"SQLite trajectory store path belongs to agent {marker.agent_id}; requested agent {requested_agent_id}."
            )
        agent_id = requested_agent_id or marker.agent_id or "jarvis"
        db_path = marker.store_path
    else:
        agent_id = requested_agent_id or "jarvis"
        db_path = store_path

    options = {
        "agent_id": agent_id,
        "path": db_path,
    }
    if params.get("env"):
        options["env"] = params["env"]

    return SqliteTrajectoryRuntimeSink(
        options=options,
        session_id=params.get("sessionId", ""),
        max_bytes=params.get("maxRuntimeBytes") or TRAJECTORY_RUNTIME_CAPTURE_MAX_BYTES
    )

def load_sqlite_trajectory_runtime_event_rows_sync(scope: Dict[str, Any]) -> List[Dict[str, Any]]:
    requested_agent_id = scope.get("agentId")
    store_path = scope.get("storePath")
    
    if not store_path:
        return []
        
    marker = parse_sqlite_session_file_marker(store_path)
    if marker:
        agent_id = requested_agent_id or marker.agent_id or "jarvis"
        db_path = marker.store_path
    else:
        agent_id = requested_agent_id or "jarvis"
        db_path = store_path

    options = {
        "agent_id": agent_id,
        "path": db_path,
    }
    if scope.get("env"):
        options["env"] = scope["env"]

    db_handle = open_agent_database(options)
    ensure_trajectory_runtime_schema(db_handle.db)
    
    query = "SELECT seq, event_json FROM trajectory_runtime_events WHERE session_id = ?"
    args = [scope.get("sessionId", "")]
    
    after_seq = scope.get("afterSeq")
    if after_seq is not None:
        query += " AND seq > ?"
        args.append(after_seq)
        
    query += " ORDER BY seq ASC"
    
    max_events = scope.get("maxEvents")
    if max_events is not None:
        query += " LIMIT ?"
        args.append(max_events)
        
    rows = db_handle.db.execute(query, tuple(args)).fetchall()
    
    result = []
    for r in rows:
        result.append({
            "seq": r[0],
            "event": json.loads(r[1])
        })
    return result
