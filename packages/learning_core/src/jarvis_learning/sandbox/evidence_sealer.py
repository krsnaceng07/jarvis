"""Cryptographic event hash chain and DPAPI/HMAC-SHA256 evidence sealing for Track 2.3.

Provides:
- Incremental SHA-256 event hash chain (H_n = SHA-256(H_{n-1} || canonical_event_bytes))
- Canonical JSON serialization with deterministic key ordering
- Local machine DPAPI protection and HMAC-SHA256 attestation
- Anti-tamper digest verification
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import hashlib
import hmac
import json
import logging
import os
import platform
from typing import Any

logger = logging.getLogger(__name__)


class EventHashChain:
    """Tamper-evident incremental hash chain for sandbox validation events."""

    def __init__(self, genesis_seed: str = "0" * 64) -> None:
        self._current_hash = genesis_seed
        self._event_count = 0

    @property
    def current_hash(self) -> str:
        return self._current_hash

    @property
    def event_count(self) -> int:
        return self._event_count

    def add_event(self, event_data: dict[str, Any]) -> str:
        """Append event to hash chain and return new digest."""
        canonical_bytes = json.dumps(event_data, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
        payload = self._current_hash.encode("ascii") + canonical_bytes
        self._current_hash = hashlib.sha256(payload).hexdigest()
        self._event_count += 1
        return self._current_hash


class SandboxEvidenceSealer:
    """Computes SHA-256 integrity digests, DPAPI-protected keys, and HMAC signatures."""

    @classmethod
    def compute_sha256_digest(cls, manifest_dict: dict[str, Any]) -> str:
        """Compute SHA-256 digest over normalized JSON excluding attestation and seal_verified blocks."""
        clean_copy = {
            k: v for k, v in manifest_dict.items() if k not in ("attestation", "seal_verified")
        }
        serialized = json.dumps(clean_copy, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    @classmethod
    def derive_machine_key(cls, salt: str = "JARVIS_TRACK23_SANDBOX") -> bytes:
        """Derive a consistent machine-bound secret key using host attributes."""
        machine_ident = (
            f"{platform.node()}:{platform.machine()}:{os.environ.get('COMPUTERNAME', '')}:{salt}"
        )
        return hashlib.sha256(machine_ident.encode("utf-8")).digest()

    @classmethod
    def protect_dpapi(cls, data: bytes) -> bytes | None:
        """Protect sensitive bytes using Windows DPAPI CryptProtectData."""
        if platform.system() != "Windows" or os.name != "nt":
            return None
        try:

            class DATA_BLOB(ctypes.Structure):
                _fields_ = [
                    ("cbData", wintypes.DWORD),
                    ("pbData", ctypes.POINTER(ctypes.c_byte)),
                ]

            crypt32 = ctypes.windll.crypt32  # type: ignore[attr-defined]
            kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]

            in_buf = (ctypes.c_byte * len(data)).from_buffer_copy(data)
            in_blob = DATA_BLOB(len(data), in_buf)
            out_blob = DATA_BLOB()

            CRYPTPROTECT_UI_FORBIDDEN = 0x01
            if crypt32.CryptProtectData(
                ctypes.byref(in_blob),
                "JarvisSandboxAttestationKey",
                None,
                None,
                None,
                CRYPTPROTECT_UI_FORBIDDEN,
                ctypes.byref(out_blob),
            ):
                result = ctypes.string_at(out_blob.pbData, out_blob.cbData)
                kernel32.LocalFree(out_blob.pbData)
                return result
        except Exception as exc:
            logger.warning("DPAPI protect failed: %s", exc)
        return None

    @classmethod
    def sign_attestation(
        cls,
        digest: str,
        secret_key: bytes | None = None,
        operator_id: str = "JARVIS_SANDBOX_OPERATOR",
    ) -> dict[str, str]:
        """Generate HMAC-SHA256 signature and attestation record."""
        key = secret_key or cls.derive_machine_key()
        signature = hmac.new(key, digest.encode("utf-8"), hashlib.sha256).hexdigest()
        return {
            "operator_id": operator_id,
            "algorithm": "HMAC-SHA256",
            "integrity_digest": digest,
            "signature": signature,
        }

    @classmethod
    def verify_seal(
        cls,
        manifest_dict: dict[str, Any],
        secret_key: bytes | None = None,
    ) -> bool:
        """Verify the integrity digest and cryptographic signature of the evidence manifest."""
        attestation = manifest_dict.get("attestation")
        if not attestation or not isinstance(attestation, dict):
            return False

        expected_sig = attestation.get("signature")
        if not expected_sig:
            return False

        computed_digest = cls.compute_sha256_digest(manifest_dict)
        if computed_digest != attestation.get("integrity_digest"):
            return False

        key = secret_key or cls.derive_machine_key()
        actual_sig = hmac.new(key, computed_digest.encode("utf-8"), hashlib.sha256).hexdigest()
        return hmac.compare_digest(actual_sig, expected_sig)


__all__ = ["EventHashChain", "SandboxEvidenceSealer"]
