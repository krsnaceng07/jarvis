"""Test Logbook node-host screenshot subprocess and deadline handling.

Ported from openclaw-main/extensions/logbook/src/node-host.test.ts.
"""

from __future__ import annotations

import subprocess
from unittest.mock import patch

from extensions.logbook.src.node_host import handle_logbook_snapshot


def test_aborts_stalled_capture_before_deadline() -> None:
    with patch("sys.platform", "darwin"):
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd=["screencapture"], timeout=25.0)

            res = handle_logbook_snapshot({})
            assert "error" in res
            assert "timed out" in res["error"].lower() or "expired" in res["error"].lower()


def test_rejects_on_non_darwin_platform() -> None:
    with patch("sys.platform", "linux"):
        res = handle_logbook_snapshot({})
        assert "not supported on linux" in res.get("error", "")
