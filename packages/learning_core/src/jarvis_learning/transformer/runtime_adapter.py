"""Runtime adapter integrating NanoTransformer into Wave 3 LocalModel architecture."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
import uuid
import numpy as np

from jarvis_learning.models.base import LocalModel, ToolPrediction
from jarvis_learning.models.calibration import ConfidenceCalibrator
from jarvis_learning.transformer.abstention import AbstentionConfig
from jarvis_learning.transformer.checkpoint import (
    CheckpointMetadata,
    load_checkpoint,
    save_checkpoint,
)
from jarvis_learning.transformer.config import TransformerConfig
from jarvis_learning.transformer.heads import LastValidTokenPooling, ToolClassificationHead
from jarvis_learning.transformer.model import NanoTransformer
from jarvis_learning.transformer.tokenizer import ByteTokenizer


class TransformerToolPolicyModel(LocalModel):
    """Deep learning Tool Policy Model powered by NanoTransformer."""

    def __init__(
        self,
        model_id: str = "nano_transformer_tool_policy",
        version: str = "v1.0.0",
        config: TransformerConfig | None = None,
        abstention_config: AbstentionConfig | None = None,
    ) -> None:
        super().__init__(target="tool_policy", model_id=model_id, version=version)
        self.config = config or TransformerConfig(
            vocab_size=260,
            max_seq_len=64,
            d_model=32,
            n_heads=2,
            d_ff=64,
            n_layers=2,
        )
        self.abstention_config = abstention_config or AbstentionConfig()
        self.tokenizer = ByteTokenizer()
        self.pooling = LastValidTokenPooling()
        self.calibrator = ConfidenceCalibrator()

        self.model: NanoTransformer | None = None
        self.head: ToolClassificationHead | None = None
        self.classes: list[str] = []

        # Safe default configuration (disabled by default, shadow-only)
        self.transformer_runtime_enabled: bool = False
        self.transformer_shadow_mode: bool = True
        self.transformer_auto_promotion: bool = False

        self._tool_metadata: dict[str, dict[str, Any]] = {
            "browser.navigate_tab": {
                "action_type": "navigate",
                "risk_level": "low",
                "strategy": "deterministic",
            },
            "browser.new_tab": {
                "action_type": "navigate",
                "risk_level": "low",
                "strategy": "context_extraction",
            },
            "volume.set": {
                "action_type": "set_state",
                "risk_level": "low",
                "strategy": "deterministic",
            },
            "volume.mute": {
                "action_type": "set_state",
                "risk_level": "low",
                "strategy": "deterministic",
            },
            "system.get_time": {
                "action_type": "read",
                "risk_level": "low",
                "strategy": "deterministic",
            },
            "app.focus": {
                "action_type": "set_state",
                "risk_level": "low",
                "strategy": "deterministic",
            },
            "app.launch": {
                "action_type": "execute",
                "risk_level": "medium",
                "strategy": "context_extraction",
            },
            "filesystem.read": {
                "action_type": "read",
                "risk_level": "low",
                "strategy": "context_extraction",
            },
            "filesystem.write": {
                "action_type": "execute",
                "risk_level": "high",
                "strategy": "llm_required",
            },
            "filesystem.delete": {
                "action_type": "destructive",
                "risk_level": "destructive",
                "strategy": "llm_required",
            },
            "system.shell": {
                "action_type": "destructive",
                "risk_level": "destructive",
                "strategy": "llm_required",
            },
        }

    def init_model(self, classes: list[str]) -> None:
        """Initializes model trunk and classification head for given classes."""
        self.classes = list(classes)
        self.model = NanoTransformer(self.config)
        self.head = ToolClassificationHead(self.config.d_model, num_classes=len(self.classes))
        self._is_loaded = True

    def predict(self, input_data: dict[str, Any]) -> ToolPrediction:
        """Predicts tool selection with crash/timeout fallback and abstention gates."""
        if not self._is_loaded or self.model is None or self.head is None:
            return ToolPrediction(tool_name="", raw_confidence=0.0, calibrated_confidence=0.0)

        # Crash & Timeout Fallback Guard
        try:
            user_val = input_data.get("user_input")
            if user_val is None or not isinstance(user_val, str):
                return ToolPrediction(
                    tool_name="",
                    raw_confidence=0.0,
                    calibrated_confidence=0.0,
                    risk_level="high",
                    argument_strategy="llm_required",
                )

            user_input = user_val.strip()
            if not user_input:
                return ToolPrediction(
                    tool_name="",
                    raw_confidence=0.0,
                    calibrated_confidence=0.0,
                    risk_level="high",
                    argument_strategy="llm_required",
                )

            # Tokenize input
            token_ids = self.tokenizer.encode(user_input, add_bos=True, add_eos=False)
            if len(token_ids) > self.config.max_seq_len:
                token_ids = token_ids[: self.config.max_seq_len]

            input_arr = token_ids[np.newaxis, :]  # Shape: (1, T)
            mask = np.ones_like(input_arr, dtype=bool)

            # Forward pass through trunk, pooling, and head
            hidden, _ = self.model.forward(input_arr, padding_mask=mask, causal=True)
            pooled = self.pooling.forward(hidden, padding_mask=mask)
            logits = self.head.forward(pooled)[0]  # Shape: (num_classes,)

            # Check for invalid numerical states
            if np.any(np.isnan(logits)) or np.any(np.isinf(logits)):
                return ToolPrediction(
                    tool_name="",
                    raw_confidence=0.0,
                    calibrated_confidence=0.0,
                    risk_level="high",
                    argument_strategy="llm_required",
                )

            # Softmax
            exp_logits = np.exp(logits - np.max(logits))
            probs = exp_logits / np.sum(exp_logits)

            best_idx = int(np.argmax(probs))
            raw_conf = float(probs[best_idx])
            calibrated_conf = self.calibrator.calibrate(raw_conf)
            tool_name = self.classes[best_idx] if best_idx < len(self.classes) else ""

            # Check abstention gate
            if calibrated_conf < self.abstention_config.min_calibrated_confidence:
                return ToolPrediction(
                    tool_name=tool_name,
                    raw_confidence=raw_conf,
                    calibrated_confidence=calibrated_conf,
                    confidence=calibrated_conf,
                    model_id=self.model_id,
                    model_version=self.version,
                    task_family="tool_policy",
                    label_id=int(best_idx),
                    is_finite=bool(np.all(np.isfinite(probs))),
                    prediction_id=f"pred_{uuid.uuid4().hex[:8]}",
                    argument_strategy="llm_required",
                )

            meta = self._tool_metadata.get(
                tool_name,
                {"action_type": "execute", "risk_level": "medium", "strategy": "llm_required"},
            )

            # Alternatives
            alt_indices = np.argsort(probs)[::-1][1:4]
            alternatives = tuple(
                (self.classes[idx], float(probs[idx]))
                for idx in alt_indices
                if idx < len(self.classes)
            )

            return ToolPrediction(
                tool_name=tool_name,
                raw_confidence=raw_conf,
                calibrated_confidence=calibrated_conf,
                confidence=calibrated_conf,
                model_id=self.model_id,
                model_version=self.version,
                task_family="tool_policy",
                label_id=int(best_idx),
                is_finite=bool(np.all(np.isfinite(probs))),
                prediction_id=f"pred_{uuid.uuid4().hex[:8]}",
                action_type=meta.get("action_type", "execute"),
                risk_level=meta.get("risk_level", "medium"),
                argument_strategy=meta.get("strategy", "deterministic"),
                alternatives=alternatives,
            )

        except Exception as e:
            import logging

            logging.getLogger(__name__).warning("predict failed: %s", e, exc_info=True)
            # Cleanly catch and fallback on ANY runtime crash / error
            return ToolPrediction(
                tool_name="",
                raw_confidence=0.0,
                calibrated_confidence=0.0,
                confidence=0.0,
                model_id=self.model_id,
                model_version=self.version,
                task_family="tool_policy",
                is_finite=False,
                risk_level="high",
                argument_strategy="llm_required",
            )

    def load(self, artifact_dir: Path) -> None:
        """Loads weights and metadata from checkpoint bundle with full verification."""
        artifact_dir = Path(artifact_dir)
        classes_file = artifact_dir / "classes.json"
        if classes_file.exists():
            with open(classes_file, "r", encoding="utf-8") as f:
                self.classes = json.load(f)

        weights, meta = load_checkpoint(
            artifact_dir,
            expected_task="tool_policy",
            expected_tokenizer_checksum=self.tokenizer.metadata.checksum,
        )

        self.config = TransformerConfig.from_dict(meta.config)
        self.version = meta.model_version
        self.init_model(self.classes)

        if self.model is None or self.head is None:
            raise RuntimeError("Failed to initialize model architecture during load")

        # Restore complete Transformer trunk weights
        self.model.set_weights(weights)

        # Restore classification head weights with strict validation
        from jarvis_learning.transformer.block import _validate_tensor

        head_w = weights.get("head.w", weights.get("head_w"))
        head_b = weights.get("head.b", weights.get("head_b"))
        if head_w is None or head_b is None:
            from jarvis_learning.transformer.errors import CheckpointCompatibilityError

            raise CheckpointCompatibilityError(
                "Missing classification head parameters in checkpoint"
            )

        self.head.w = _validate_tensor(head_w, (self.config.d_model, len(self.classes)), "head.w")
        self.head.b = _validate_tensor(head_b, (len(self.classes),), "head.b")

        self._is_loaded = True

    def save(
        self,
        artifact_dir: Path,
        model_version: str | None = None,
        allow_overwrite: bool = False,
    ) -> CheckpointMetadata:
        """Saves current weights and metadata using full serialization and atomic publication."""
        if not self._is_loaded or self.model is None or self.head is None:
            raise RuntimeError("Model is not loaded or initialized")

        artifact_dir = Path(artifact_dir)
        artifact_dir.mkdir(parents=True, exist_ok=True)

        classes_file = artifact_dir / "classes.json"
        with open(classes_file, "w", encoding="utf-8") as f:
            json.dump(self.classes, f, indent=2)

        # Full weight dictionary from entire transformer trunk
        weights_dict = self.model.get_weights()
        weights_dict["head.w"] = self.head.w.copy()
        weights_dict["head.b"] = self.head.b.copy()

        # Backward compatibility aliases
        weights_dict["token_embedding"] = self.model.token_embedding.weight
        weights_dict["head_w"] = self.head.w
        weights_dict["head_b"] = self.head.b

        version = model_version or self.version or "v1.0.0"

        extra_files = {
            "classes.json": json.dumps(self.classes, indent=2),
        }

        meta = save_checkpoint(
            checkpoint_dir=artifact_dir,
            model_task="tool_policy",
            config=self.config,
            weights_dict=weights_dict,
            tokenizer_checksum=self.tokenizer.metadata.checksum,
            model_version=version,
            allow_overwrite=allow_overwrite,
            extra_files=extra_files,
        )
        return meta

    def unload(self) -> None:
        self.model = None
        self.head = None
        self._is_loaded = False
