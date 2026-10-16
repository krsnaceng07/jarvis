"""A2A HTTP dispatch client."""

from __future__ import annotations

import json
import logging
from typing import Any
from urllib.request import Request, urlopen

from .protocol import A2ATaskEnvelope

logger = logging.getLogger("jarvis.extensions.a2a")


class A2AClient:
    """Client for delegating tasks between agents over A2A protocol."""

    def __init__(self, endpoint: str, api_key: str | None = None) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.api_key = api_key

    def dispatch_task(self, envelope: A2ATaskEnvelope) -> dict[str, Any]:
        """Dispatch task envelope to target agent endpoint."""
        url = (
            f"{self.endpoint}/a2a/v1/tasks"
            if not self.endpoint.endswith("/tasks")
            else self.endpoint
        )
        data = json.dumps(envelope.to_dict()).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            **({"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}),
        }
        req = Request(url, data=data, headers=headers)
        try:
            with urlopen(req, timeout=15) as resp:
                body = resp.read().decode("utf-8")
                return (
                    json.loads(body)
                    if body
                    else {"status": "dispatched", "task_id": envelope.task_id}
                )
        except Exception as e:
            logger.warning(f"A2A task dispatch failed: {e}")
            return {"error": str(e), "task_id": envelope.task_id}
