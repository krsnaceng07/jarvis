"""packages/voice_pipeline/src/jarvis_voice_pipeline/worker.py

Native JARVIS Worker runner for headless/background execution.
"""

from __future__ import annotations

import sys
from .terminal_app import main


def run_worker() -> int:
    """Run JARVIS worker in headless/terminal mode."""
    return main()


if __name__ == "__main__":
    sys.exit(run_worker())
