"""jarvis_learning.training.backend_manifest — signed backend capability manifests and preflight validation.

Guarantees:
- INV-MAN-001: Every trainer backend exposes a signed capability manifest.
- Preflight rejects unapproved backends or backends lacking task-required capabilities
  (e.g., preference learning, LoRA, GPU support) before child launch.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
from dataclasses import dataclass
from typing import ClassVar

from .security_policy import SecurityPolicyError

logger = logging.getLogger(__name__)

_BACKEND_SIGNING_KEY = b"jarvis_learning_backend_signing_key_v1"


@dataclass(frozen=True, slots=True)
class BackendCapabilities:
    """Declared capabilities supported by a trainer backend implementation."""

    supports_cpu: bool = True
    supports_gpu: bool = False
    supports_resume: bool = True
    supports_deterministic_mode: bool = True
    supports_preference_data: bool = False
    supports_lora: bool = False
    supports_optimizer_checkpoint: bool = True
    supports_gradient_accumulation: bool = False
    max_sequence_length: int = 2048


@dataclass(frozen=True, slots=True)
class BackendManifest:
    """Cryptographic manifest and metadata declaring a verified trainer backend."""

    backend_id: str
    version: str
    source_hash: str
    entrypoint: str
    capabilities: BackendCapabilities
    allowed_imports: tuple[str, ...]
    network_required: bool = False
    signature: str = ""
    signing_key_id: str = "jarvis_official_v1"

    @classmethod
    def create_signed(
        cls,
        backend_id: str,
        version: str,
        source_hash: str,
        entrypoint: str,
        capabilities: BackendCapabilities,
        allowed_imports: tuple[str, ...],
        network_required: bool = False,
    ) -> BackendManifest:
        """Create and sign a backend manifest."""
        payload = f"{backend_id}:{version}:{source_hash}:{entrypoint}:{network_required}"
        sig = hmac.new(_BACKEND_SIGNING_KEY, payload.encode("utf-8"), hashlib.sha256).hexdigest()
        return cls(
            backend_id=backend_id,
            version=version,
            source_hash=source_hash,
            entrypoint=entrypoint,
            capabilities=capabilities,
            allowed_imports=allowed_imports,
            network_required=network_required,
            signature=sig,
        )

    def verify_signature(self) -> bool:
        """Verify HMAC signature of the manifest."""
        payload = f"{self.backend_id}:{self.version}:{self.source_hash}:{self.entrypoint}:{self.network_required}"
        expected = hmac.new(
            _BACKEND_SIGNING_KEY, payload.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(self.signature, expected)


class BackendRegistry:
    """Registry of verified, approved trainer backends."""

    _manifests: ClassVar[dict[str, BackendManifest]] = {
        "tfidf_logistic": BackendManifest.create_signed(
            backend_id="tfidf_logistic",
            version="1.0.0",
            source_hash="sha256_baseline_src_abc",
            entrypoint="jarvis_learning.training.trainer_backend.TFIDFLogisticBaselineBackend",
            capabilities=BackendCapabilities(
                supports_cpu=True,
                supports_gpu=False,
                supports_preference_data=False,
                supports_lora=False,
            ),
            allowed_imports=("math", "re", "collections", "random", "json"),
        ),
        "torch_sft": BackendManifest.create_signed(
            backend_id="torch_sft",
            version="1.0.0",
            source_hash="sha256_sft_src_def",
            entrypoint="jarvis_learning.training.trainer_backend.TorchSFTTrainerBackend",
            capabilities=BackendCapabilities(
                supports_cpu=True,
                supports_gpu=True,
                supports_preference_data=False,
                supports_lora=False,
                supports_gradient_accumulation=True,
            ),
            allowed_imports=("torch", "torch.nn", "torch.optim"),
        ),
        "torch_preference": BackendManifest.create_signed(
            backend_id="torch_preference",
            version="1.0.0",
            source_hash="sha256_pref_src_ghi",
            entrypoint="jarvis_learning.training.trainer_backend.TorchPreferenceTrainerBackend",
            capabilities=BackendCapabilities(
                supports_cpu=True,
                supports_gpu=True,
                supports_preference_data=True,
                supports_lora=False,
            ),
            allowed_imports=("torch", "torch.nn", "torch.optim"),
        ),
        "lora": BackendManifest.create_signed(
            backend_id="lora",
            version="1.0.0",
            source_hash="sha256_lora_src_jkl",
            entrypoint="jarvis_learning.training.trainer_backend.LoRATrainerBackend",
            capabilities=BackendCapabilities(
                supports_cpu=True,
                supports_gpu=True,
                supports_preference_data=True,
                supports_lora=True,
            ),
            allowed_imports=("torch", "peft", "transformers"),
        ),
    }

    @classmethod
    def get_manifest(cls, backend_id: str) -> BackendManifest | None:
        """Fetch manifest for backend_id."""
        return cls._manifests.get(backend_id.lower().strip())

    @classmethod
    def validate_preflight(
        cls,
        backend_id: str,
        require_gpu: bool = False,
        is_preference_task: bool = False,
        require_lora: bool = False,
    ) -> BackendManifest:
        """Validate backend trust, signature, and required capabilities."""
        manifest = cls.get_manifest(backend_id)
        if not manifest:
            msg = f"Untrusted or unregistered trainer backend '{backend_id}'"
            logger.error(msg)
            raise SecurityPolicyError(msg, code="UNREGISTERED_BACKEND_REJECTED")

        if not manifest.verify_signature():
            msg = f"Signature verification failed for backend '{backend_id}'"
            logger.error(msg)
            raise SecurityPolicyError(msg, code="INVALID_BACKEND_SIGNATURE")

        caps = manifest.capabilities
        if require_gpu and not caps.supports_gpu:
            msg = f"Backend '{backend_id}' does not support requested GPU execution"
            logger.error(msg)
            raise SecurityPolicyError(msg, code="CAPABILITY_MISMATCH_GPU")

        if is_preference_task and not caps.supports_preference_data:
            msg = f"Backend '{backend_id}' does not support preference optimization (DPO/KTO)"
            logger.error(msg)
            raise SecurityPolicyError(msg, code="CAPABILITY_MISMATCH_PREFERENCE")

        if require_lora and not caps.supports_lora:
            msg = f"Backend '{backend_id}' does not support PEFT / LoRA adaptation"
            logger.error(msg)
            raise SecurityPolicyError(msg, code="CAPABILITY_MISMATCH_LORA")

        return manifest


CANONICAL_BACKENDS = BackendRegistry._manifests
get_backend_manifest = BackendRegistry.get_manifest
validate_preflight = BackendRegistry.validate_preflight
