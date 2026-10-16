"""src.security.audit_logger — Structured forensic security audit logger.

Matches OpenClaw tools/audit/audit_logger.py:
- Append-only JSONL security event stream
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass
from typing import Any, Optional

logger = logging.getLogger("jarvis.security.audit")


@dataclass(frozen=True, slots=True)
class SecurityAuditEvent:
    timestamp: float
    event_type: str
    principal_id: str
    channel: str
    action: str
    resource: str
    risk_level: str
    decision: str
    reason: str
    correlation_id: str
    metadata: Optional[dict[str, Any]] = None


class SecurityAuditLogger:
    def __init__(self, log_path: str = r"E:\jarvis\logs\security_audit.jsonl"):
        self._log_path = log_path
        os.makedirs(os.path.dirname(self._log_path), exist_ok=True)

    def log_event(self, event: SecurityAuditEvent) -> None:
        payload = asdict(event)
        line = json.dumps(payload, ensure_ascii=False) + "\n"
        try:
            with open(self._log_path, "a", encoding="utf-8") as f:
                f.write(line)
        except Exception as e:
            logger.error("Failed to write security audit event: %s", e)
