"""jarvis_retry — Async retry with bounded attempts + backoff.

OpenClaw parity: mirrors
``packages/retry/src/`` (``retryAsync`` helper).

This package re-exports ``jarvis_sdk.retry_runtime.retry_async``.
The re-export shim is temporary: a follow-up phase will
physically move the module here and update all
``jarvis_sdk.retry_runtime`` import sites to
``jarvis_retry.retry_async``.
"""
from __future__ import annotations

from jarvis_sdk.retry_runtime import retry_async  # noqa: F401

__all__ = ["retry_async"]
