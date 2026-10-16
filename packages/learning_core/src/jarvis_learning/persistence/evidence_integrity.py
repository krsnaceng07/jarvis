"""Cryptographic sealing and DPAPI/HMAC-SHA256 attestation for reboot persistence evidence.

Ensures evidence artifacts and pre-reboot manifests are tamper-evident and authenticated:
- Canonical JSON SHA-256 digest computation
- Windows DPAPI or machine-bound HMAC-SHA256 signature generation
- Signature verification and anti-tamper checking
"""

from __future__ import annotations

import dataclasses
import hashlib
import hmac
import json
import logging
import os
from pathlib import Path
import time
from typing import Any

logger = logging.getLogger(__name__)


class AttestationKeyProvider:
    """Manages secure key derivation for reboot persistence attestation."""

    KEY_FILE = ".attestation_key"

    @classmethod
    def get_or_create_key(cls, lab_dir: Path, machine_guid: str | None = None) -> bytes:
        """Derive or load an attestation key bound to the local machine and directory."""
        key_path = lab_dir / cls.KEY_FILE
        if key_path.exists():
            try:
                raw_bytes = key_path.read_bytes()
                # If on Windows and DPAPI was used
                if os.name == "nt" and raw_bytes.startswith(b"DPAPI:"):
                    unprotected = cls._unprotect_dpapi(raw_bytes[6:])
                    if unprotected:
                        return unprotected
                return raw_bytes
            except Exception as exc:
                logger.warning("Failed loading attestation key: %s, regenerating", exc)

        # Generate fresh 32-byte key
        fresh_key = os.urandom(32)
        if machine_guid:
            # Mix machine GUID to bind to physical host
            fresh_key = hashlib.sha256(fresh_key + machine_guid.encode("utf-8")).digest()

        lab_dir.mkdir(parents=True, exist_ok=True)
        try:
            if os.name == "nt":
                protected = cls._protect_dpapi(fresh_key)
                if protected:
                    key_path.write_bytes(b"DPAPI:" + protected)
                    return fresh_key

            key_path.write_bytes(fresh_key)
        except Exception as exc:
            logger.warning("Could not persist attestation key file: %s", exc)

        return fresh_key

    @classmethod
    def _protect_dpapi(cls, data: bytes) -> bytes | None:
        """Protect data using Windows DPAPI (CryptProtectData via ctypes)."""
        if os.name != "nt":
            return None
        try:
            import ctypes
            from ctypes import wintypes

            class DATA_BLOB(ctypes.Structure):
                _fields_ = [
                    ("cbData", wintypes.DWORD),
                    ("pbData", ctypes.POINTER(ctypes.c_byte)),
                ]

            crypt32 = ctypes.windll.crypt32  # type: ignore[attr-defined]
            in_blob = DATA_BLOB(
                len(data),
                ctypes.cast(
                    ctypes.create_string_buffer(data, len(data)), ctypes.POINTER(ctypes.c_byte)
                ),
            )
            out_blob = DATA_BLOB()

            # CRYPTPROTECT_UI_FORBIDDEN = 0x1
            if crypt32.CryptProtectData(
                ctypes.byref(in_blob),
                "JARVIS_PERSISTENCE_KEY",
                None,
                None,
                None,
                0x1,
                ctypes.byref(out_blob),
            ):
                result = ctypes.string_at(out_blob.pbData, out_blob.cbData)
                kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
                kernel32.LocalFree(out_blob.pbData)
                return result
            return None
        except Exception as exc:
            logger.debug("DPAPI CryptProtectData failed: %s", exc)
            return None

    @classmethod
    def _unprotect_dpapi(cls, data: bytes) -> bytes | None:
        """Unprotect data using Windows DPAPI (CryptUnprotectData via ctypes)."""
        if os.name != "nt":
            return None
        try:
            import ctypes
            from ctypes import wintypes

            class DATA_BLOB(ctypes.Structure):
                _fields_ = [
                    ("cbData", wintypes.DWORD),
                    ("pbData", ctypes.POINTER(ctypes.c_byte)),
                ]

            crypt32 = ctypes.windll.crypt32  # type: ignore[attr-defined]
            in_blob = DATA_BLOB(
                len(data),
                ctypes.cast(
                    ctypes.create_string_buffer(data, len(data)), ctypes.POINTER(ctypes.c_byte)
                ),
            )
            out_blob = DATA_BLOB()

            # CRYPTPROTECT_UI_FORBIDDEN = 0x1
            if crypt32.CryptUnprotectData(
                ctypes.byref(in_blob),
                None,
                None,
                None,
                None,
                0x1,
                ctypes.byref(out_blob),
            ):
                result = ctypes.string_at(out_blob.pbData, out_blob.cbData)
                kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
                kernel32.LocalFree(out_blob.pbData)
                return result
            return None
        except Exception as exc:
            logger.debug("DPAPI CryptUnprotectData failed: %s", exc)
            return None


@dataclasses.dataclass(frozen=True)
class AttestationEnvelope:
    """Cryptographic attestation signature block."""

    sha256_digest: str
    hmac_sha256: str
    key_id: str
    sealed_at_utc: str

    def to_dict(self) -> dict[str, str]:
        return dataclasses.asdict(self)


class PersistenceIntegritySealer:
    """Computes and validates SHA-256 and HMAC-SHA256 signatures for persistence records."""

    @staticmethod
    def compute_sha256_digest(payload: dict[str, Any]) -> str:
        """Compute SHA-256 digest of payload excluding signature/attestation fields."""
        clean = {
            k: v
            for k, v in payload.items()
            if k not in ("attestation", "signature", "manifest_signature")
        }
        normalized = json.dumps(clean, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    @classmethod
    def seal(
        cls,
        payload: dict[str, Any],
        secret_key: bytes,
        key_id: str = "dpapi_machine_key",
    ) -> dict[str, Any]:
        """Attach cryptographic attestation to payload."""
        digest = cls.compute_sha256_digest(payload)
        sig = hmac.new(secret_key, digest.encode("utf-8"), hashlib.sha256).hexdigest()
        now_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        envelope = AttestationEnvelope(
            sha256_digest=digest,
            hmac_sha256=sig,
            key_id=key_id,
            sealed_at_utc=now_utc,
        )

        copy_payload = dict(payload)
        copy_payload["attestation"] = envelope.to_dict()
        return copy_payload

    @classmethod
    def verify(cls, payload: dict[str, Any], secret_key: bytes) -> tuple[bool, str]:
        """Verify that payload has not been tampered with and matches HMAC signature."""
        attestation = payload.get("attestation")
        if not isinstance(attestation, dict):
            return False, "Missing or invalid attestation block"

        recorded_digest = attestation.get("sha256_digest")
        recorded_hmac = attestation.get("hmac_sha256")

        if not recorded_digest or not recorded_hmac:
            return False, "Attestation block missing required digest or signature"

        recomputed_digest = cls.compute_sha256_digest(payload)
        if recomputed_digest != recorded_digest:
            return (
                False,
                f"SHA-256 digest mismatch: payload has been modified ({recomputed_digest} != {recorded_digest})",
            )

        expected_hmac = hmac.new(
            secret_key, recomputed_digest.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(expected_hmac, recorded_hmac):
            return False, "HMAC-SHA256 signature mismatch"

        return True, "Attestation valid and intact"


__all__ = [
    "AttestationEnvelope",
    "AttestationKeyProvider",
    "PersistenceIntegritySealer",
]
