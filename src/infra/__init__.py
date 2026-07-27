"""jarvis.infra — low-level runtime infrastructure helpers.

OpenClaw parity: mirrors ``src/infra/``.
"""
from __future__ import annotations

from .abort_signal import AbortError, create_abort_error, is_abort_error  # noqa: F401
