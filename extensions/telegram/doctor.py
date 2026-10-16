"""Doctor contract for the Telegram extension.

This is the Phase 3 parity surface the tests import from
``extensions.telegram.doctor``. It exposes a single ``detect_telegram_credentials``
check that returns ``DoctorFinding`` instances when the channel is not configured.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.doctor import DoctorFinding, Severity


def detect_telegram_credentials(state_dir: Path, _config: dict[str, Any]) -> list[DoctorFinding]:
    """Detect whether Telegram bot credentials are missing."""
    import os

    state_path = state_dir / "telegram.json"
    if state_path.exists():
        return []
    token = os.environ.get("JARVIS_TELEGRAM_BOT_TOKEN") or os.environ.get("TELEGRAM_BOT_TOKEN")
    if token:
        return []

    return [
        DoctorFinding(
            plugin_id="telegram",
            label="Telegram bot token missing",
            path=state_path,
            count=1,
            severity=Severity.ERROR,
            message="Telegram bot token is not configured.",
        )
    ]


__all__ = ["detect_telegram_credentials"]
