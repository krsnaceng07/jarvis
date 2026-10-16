"""ClickClack interactive session state."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field


@dataclass(slots=True)
class ClickClackSession:
    session_id: str = field(default_factory=lambda: f"cc_{uuid.uuid4().hex[:8]}")
    user_id: str = "local_user"
    active: bool = True
    created_at: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)

    def touch(self) -> None:
        self.last_activity = time.time()
