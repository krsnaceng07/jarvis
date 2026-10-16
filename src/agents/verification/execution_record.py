"""jarvis.agents.verification.execution_record — Machine-readable execution logs.

Every important real-world action maintains an immutable audit record:
  execution_id
  task_id
  session_key
  timestamp
  tool_name
  arguments
  status
  raw_output
  verification
  affected_files
"""

from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

from .execution_verifier import VerificationOutcome


@dataclass(slots=True)
class ExecutionRecord:
    """Audit record of a single tool execution."""

    execution_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    task_id: Optional[str] = None
    session_key: str = "agent:main:main"
    timestamp: float = field(default_factory=time.time)
    tool_name: str = ""
    arguments: dict[str, Any] = field(default_factory=dict)
    status: str = "success"  # "success" | "failed" | "rejected"
    raw_output: str = ""
    verification: Optional[VerificationOutcome] = None
    affected_files: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if self.verification:
            data["verification"] = self.verification.to_dict()
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExecutionRecord:
        d = dict(data)
        v_data = d.pop("verification", None)
        verification = VerificationOutcome(**v_data) if isinstance(v_data, dict) else v_data
        return cls(verification=verification, **d)

    def summary(self) -> str:
        status_sym = "✅" if self.status == "success" else "❌"
        verif_str = " (Verified)" if self.verification and self.verification.verified else ""
        return (
            f"[{self.tool_name}] {status_sym} {self.status}{verif_str}: "
            f"{self.raw_output[:120].strip()}"
        )
