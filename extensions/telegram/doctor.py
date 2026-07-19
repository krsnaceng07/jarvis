"""Doctor contract for the Telegram channel.

Mirrors the pattern in ``extensions/memory_core/doctor.py``.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

from jarvis.doctor import DoctorFinding

if TYPE_CHECKING:
    pass


def detect_telegram_credentials(state_dir: Path, config: dict[str, Any]) -> list[DoctorFinding]:
    """Flag missing Telegram bot credentials.

    Phase 3 doctor contract. We treat the absence of a bot_token
    as a warning (the operator can pair at runtime via
    ``jarvis telegram setup``).
    """
    env_token = os.environ.get("JARVIS_TELEGRAM_BOT_TOKEN")
    # The runtime's default() reads from $JARVIS_DATA_DIR/telegram.json
    # — we don't import the runtime here to avoid pulling httpx, but
    # the JSON file path is the canonical signal.
    store = state_dir / "telegram.json"
    if env_token or store.exists():
        return []
    return [
        DoctorFinding(
            label="Telegram bot token not configured",
            path=store,
            count=0,
            details={"fix": "run 'jarvis telegram setup' or set JARVIS_TELEGRAM_BOT_TOKEN"},
        )
    ]


__all__ = ["detect_telegram_credentials"]
