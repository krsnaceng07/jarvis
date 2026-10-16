"""jarvis_learning.training.security_policy — training worker process security and isolation.

Enforces:
1. Environment secret stripping (removes API keys, passwords, tokens, auth headers).
2. Network policy (blocks outbound network traffic from training subprocesses).
3. Backend allowlisting (restricts execution to verified, registered trainer backends).
"""

from __future__ import annotations

import contextlib
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from .errors import TrainingError

logger = logging.getLogger(__name__)

# Patterns identifying sensitive credentials that must never enter worker environment
SENSITIVE_ENV_PATTERNS = (
    "KEY",
    "TOKEN",
    "SECRET",
    "PASSWORD",
    "CREDENTIAL",
    "AUTH",
    "BEARER",
    "PRIVATE",
)

# Canonical allowlist of approved trainer backend identifiers
ALLOWED_TRAINER_BACKENDS = frozenset(
    {
        "tfidf_logistic",
        "baseline",
        "torch_sft",
        "sft",
        "dpo",
        "preference",
        "torch_preference",
        "lora",
        "peft",
    }
)


class SecurityPolicyError(TrainingError):
    """Raised when security boundaries or sandbox policies are breached."""

    def __init__(self, message: str, code: str = "SECURITY_POLICY_VIOLATION") -> None:
        super().__init__(message, code=code)


@dataclass(frozen=True, slots=True)
class SecurityPolicy:
    """Configures environment sanitization, network restriction, and backend validation."""

    allow_network: bool = False
    allowlist_backends: frozenset[str] = ALLOWED_TRAINER_BACKENDS
    allowed_write_roots: tuple[Path, ...] = ()

    @contextlib.contextmanager
    def block_network_calls(self):
        """Context manager strictly disabling raw socket, DNS, and HTTP operations (INV-SEC-001)."""
        import socket

        orig_socket = socket.socket
        orig_getaddrinfo = socket.getaddrinfo

        def _blocked_socket(*args, **kwargs):
            raise SecurityPolicyError(
                "Network access disabled by SecurityPolicy (INV-SEC-001)",
                code="NETWORK_DISABLED",
            )

        def _blocked_getaddrinfo(*args, **kwargs):
            raise SecurityPolicyError(
                "DNS query blocked by SecurityPolicy (INV-SEC-001)",
                code="DNS_BLOCKED",
            )

        socket.socket = _blocked_socket
        socket.getaddrinfo = _blocked_getaddrinfo
        try:
            yield
        finally:
            socket.socket = orig_socket
            socket.getaddrinfo = orig_getaddrinfo

    def validate_file_access(self, target_path: Path | str, mode: str = "r") -> bool:
        """Enforce filesystem write boundary containment (INV-SEC-001)."""
        p = Path(target_path).resolve()
        if "w" in mode or "a" in mode or "+" in mode:
            if self.allowed_write_roots:
                is_allowed = any(
                    p == root.resolve() or root.resolve() in p.parents
                    for root in self.allowed_write_roots
                )
                if not is_allowed:
                    raise SecurityPolicyError(
                        f"Filesystem write access outside allowed roots is blocked: {p}",
                        code="WRITE_OUTSIDE_ALLOWED_ROOT",
                    )
        return True

    def scrub_environment(self, base_env: Mapping[str, str] | None = None) -> dict[str, str]:
        """Strip all sensitive environment variables from child process environment."""
        if not isinstance(self, SecurityPolicy):
            # Invoked as SecurityPolicy.scrub_environment(dirty_env)
            actual_base = self  # type: ignore[assignment]
            allow_net = False
        else:
            actual_base = base_env
            allow_net = self.allow_network

        env = dict(os.environ if actual_base is None else actual_base)
        keys_to_remove = []

        for k in env:
            upper_k = k.upper()
            if any(pattern in upper_k for pattern in SENSITIVE_ENV_PATTERNS):
                keys_to_remove.append(k)

        for k in keys_to_remove:
            del env[k]

        logger.debug(
            "Scrubbed %d sensitive environment variables from worker env", len(keys_to_remove)
        )

        # Enforce network isolation by pointing proxies to invalid loopback if network not allowed
        if not allow_net:
            env["HTTP_PROXY"] = "http://127.0.0.1:0"
            env["HTTPS_PROXY"] = "http://127.0.0.1:0"
            env["ALL_PROXY"] = "http://127.0.0.1:0"
            env["NO_PROXY"] = ""

        return env

    def validate_backend(self, backend_type: str) -> bool:
        """Verify that the requested backend is on the approved allowlist."""
        normalized = backend_type.strip().lower()
        if normalized not in self.allowlist_backends:
            msg = (
                f"Untrusted or unregistered trainer backend '{backend_type}' is rejected. "
                f"Allowed backends: {sorted(self.allowlist_backends)}"
            )
            logger.error(msg)
            raise SecurityPolicyError(msg, code="UNREGISTERED_BACKEND_REJECTED")
        return True
