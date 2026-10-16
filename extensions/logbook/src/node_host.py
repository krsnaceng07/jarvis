"""Logbook node-host command: screen capture for headless node hosts (macOS).

Nodes without the desktop app advertise ``logbook.snapshot`` so capture works
anywhere the plugin is enabled.

Mirrors OpenClaw's ``extensions/logbook/src/node-host.ts``.
"""

from __future__ import annotations

import base64
import os
import subprocess
import sys
import tempfile
import uuid
from typing import Any, Optional

LOGBOOK_SNAPSHOT_EXEC_TIMEOUT_MS: int = 25000


def _as_finite_number(value: Any) -> Optional[float]:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if value == value:  # not NaN
            return float(value)
    return None


def handle_logbook_snapshot(raw_params: Any) -> dict[str, Any]:
    """Capture screen on macOS using screencapture and downscale using sips.

    Mirrors OpenClaw's ``handleLogbookSnapshot``.
    Returns ``{"format": "jpeg", "base64": ...}`` or ``{"error": ...}``.
    """
    if sys.platform != "darwin":
        return {"error": f"logbook.snapshot is not supported on {sys.platform}"}

    params = raw_params if isinstance(raw_params, dict) else {}
    raw_screen_index = _as_finite_number(params.get("screenIndex"))
    raw_max_width = _as_finite_number(params.get("maxWidth"))
    raw_quality = _as_finite_number(params.get("quality"))

    screen_index = max(0, round(raw_screen_index)) if raw_screen_index is not None else 0
    max_width = round(raw_max_width) if (raw_max_width is not None and raw_max_width >= 480) else 1440
    quality_pct = min(
        100,
        max(
            10,
            round(
                (raw_quality if (raw_quality is not None and 0 < raw_quality <= 1) else 0.6) * 100
            ),
        ),
    )

    capture_dir = os.path.join(tempfile.gettempdir(), "openclaw", "logbook")
    os.makedirs(capture_dir, exist_ok=True)
    try:
        os.chmod(capture_dir, 0o700)
    except OSError:
        pass

    file_path = os.path.join(capture_dir, f"logbook-snapshot-{uuid.uuid4()}.jpg")

    try:
        # Pre-create owner-only
        with open(file_path, "wb"):
            pass
        try:
            os.chmod(file_path, 0o600)
        except OSError:
            pass

        timeout_sec = LOGBOOK_SNAPSHOT_EXEC_TIMEOUT_MS / 1000.0

        # -x: no capture sound; -C: include cursor; -D is 1-based display index
        subprocess.run(
            ["screencapture", "-x", "-C", "-D", str(screen_index + 1), "-t", "jpg", file_path],
            check=True,
            timeout=timeout_sec,
            capture_output=True,
        )

        subprocess.run(
            [
                "sips",
                "--resampleHeightWidthMax",
                str(max_width),
                "-s",
                "format",
                "jpeg",
                "-s",
                "formatOptions",
                str(quality_pct),
                file_path,
            ],
            check=True,
            timeout=timeout_sec,
            capture_output=True,
        )

        with open(file_path, "rb") as f:
            data = f.read()

        return {
            "format": "jpeg",
            "base64": base64.b64encode(data).decode("ascii"),
        }
    except Exception as err:
        return {"error": str(err)}
    finally:
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
        except OSError:
            pass


__all__ = [
    "LOGBOOK_SNAPSHOT_EXEC_TIMEOUT_MS",
    "handle_logbook_snapshot",
]
