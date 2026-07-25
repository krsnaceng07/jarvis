"""jarvis.security — Security helpers.

OpenClaw parity: mirrors ``src/security/`` (currently a stub
in OpenClaw; the Python port provides the security runtime
helpers from `jarvis_sdk.security_runtime`).

Re-export shim: a follow-up phase will physically move
``jarvis_sdk.security_runtime`` here and update all import
sites.
"""
from __future__ import annotations

from jarvis_sdk.security_runtime import (  # noqa: F401
    resolve_secret_input_ref,
    redact_sensitive_text_runtime,
)
