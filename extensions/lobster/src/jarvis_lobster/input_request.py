"""Input Request Suspension primitives for Lobster.

Mirrors `input_request.ts` from OpenClaw.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CommandInputResume:
    """A resume token to continue execution from a suspended state."""

    resume_token: str
    approval_id: str
    approved: bool


class InputRequestSuspension(Exception):
    """Exception raised when a stage needs approval to continue."""

    def __init__(
        self, stage_index: int, prompt: str, items: list[Any], resume_token: str, approval_id: str
    ) -> None:
        super().__init__(f"Approval required for stage {stage_index}: {prompt}")
        self.stage_index = stage_index
        self.prompt = prompt
        self.items = items
        self.resume_token = resume_token
        self.approval_id = approval_id

    def to_envelope(self) -> dict[str, Any]:
        """Format as the requiresApproval envelope."""
        return {
            "type": "approval_request",
            "prompt": self.prompt,
            "items": self.items,
            "resumeToken": self.resume_token,
            "approvalId": self.approval_id,
        }


def generate_resume_token() -> tuple[str, str]:
    """Generate a random resume token and short approval ID."""
    token = uuid.uuid4().hex
    return token, token[:8]
