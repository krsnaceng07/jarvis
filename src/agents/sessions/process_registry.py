"""jarvis.agents.sessions.process_registry — In-memory registry for background exec sessions.

Tracks running/backgrounded sessions, bounded pending output, and finished session retention.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Literal, Any


# Lifecycle status recorded for background process sessions.
ProcessStatus = Literal["running", "completed", "failed", "killed"]

DEFAULT_JOB_TTL_MS = 30 * 60 * 1000  # 30 minutes
DEFAULT_PENDING_OUTPUT_CHARS = 30_000


@dataclass
class ProcessSession:
    """Mutable session state for a running background process."""

    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    command: str = ""
    session_key: Optional[str] = None
    started_at: float = field(default_factory=time.time)
    cwd: Optional[str] = None
    
    # Process management
    pid: Optional[int] = None
    # We store the opaque handle to the subprocess or asyncio task here
    proc: Optional[Any] = None  
    
    # Output limits
    max_output_chars: int = 200_000
    pending_max_output_chars: int = DEFAULT_PENDING_OUTPUT_CHARS
    
    # Aggregators
    total_output_chars: int = 0
    pending_stdout: List[str] = field(default_factory=list)
    pending_stderr: List[str] = field(default_factory=list)
    pending_stdout_chars: int = 0
    pending_stderr_chars: int = 0
    
    aggregated: str = ""
    
    # Exit conditions
    exit_code: Optional[int] = None
    exit_signal: Optional[int] = None
    exited: bool = False
    truncated: bool = False
    backgrounded: bool = False
    
    # Terminal UI state
    cursor_key_mode: Literal["unknown", "normal", "application"] = "unknown"

    def mark_exited(self, code: Optional[int], signal: Optional[int] = None) -> None:
        self.exited = True
        self.exit_code = code
        self.exit_signal = signal

    def append_stdout(self, chunk: str) -> None:
        """Appends to stdout and scans for terminal UI escape sequences."""
        self.pending_stdout.append(chunk)
        self.pending_stdout_chars += len(chunk)
        self.total_output_chars += len(chunk)
        
        # Scan for smkx (application mode) and rmkx (normal mode)
        # \x1b[?1h enables application cursor keys
        # \x1b[?1l disables application cursor keys (normal mode)
        if "\x1b[?1h" in chunk:
            self.cursor_key_mode = "application"
        elif "\x1b[?1l" in chunk:
            self.cursor_key_mode = "normal"


@dataclass
class FinishedSession:
    """Retained summary for a completed background session."""
    id: str
    command: str
    started_at: float
    ended_at: float
    cwd: Optional[str] = None
    session_key: Optional[str] = None
    exit_code: Optional[int] = None
    exit_signal: Optional[int] = None
    aggregated: str = ""
    tail: str = ""


class ProcessRegistry:
    """In-memory tracking of process sessions."""

    def __init__(self) -> None:
        self._active: Dict[str, ProcessSession] = {}
        self._finished: Dict[str, FinishedSession] = {}

    def register(self, session: ProcessSession) -> None:
        self._active[session.id] = session

    def get_active(self, session_id: str) -> Optional[ProcessSession]:
        return self._active.get(session_id)

    def get_all_active(self, session_key: Optional[str] = None) -> List[ProcessSession]:
        if session_key is None:
            return list(self._active.values())
        return [s for s in self._active.values() if s.session_key == session_key]

    def get_finished(self, session_id: str) -> Optional[FinishedSession]:
        return self._finished.get(session_id)

    def get_all_finished(self, session_key: Optional[str] = None) -> List[FinishedSession]:
        if session_key is None:
            return list(self._finished.values())
        return [s for s in self._finished.values() if s.session_key == session_key]

    def remove(self, session_id: str) -> bool:
        if session_id in self._active:
            del self._active[session_id]
            return True
        if session_id in self._finished:
            del self._finished[session_id]
            return True
        return False

    def mark_finished(self, session_id: str, code: Optional[int], signal: Optional[int] = None) -> None:
        session = self._active.get(session_id)
        if session:
            session.mark_exited(code, signal)
            tail_text = "".join(session.pending_stdout[-10:]) if session.pending_stdout else ""
            self._finished[session_id] = FinishedSession(
                id=session.id,
                command=session.command,
                started_at=session.started_at,
                ended_at=time.time(),
                cwd=session.cwd,
                session_key=session.session_key,
                exit_code=code,
                exit_signal=signal,
                aggregated=session.aggregated,
                tail=tail_text,
            )
            # Remove from active to prevent it showing as running
            del self._active[session_id]


# Global singleton for phase 1 parity
registry = ProcessRegistry()
