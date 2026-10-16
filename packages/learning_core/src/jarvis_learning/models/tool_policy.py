"""jarvis_learning.models.tool_policy — Model A: Tool Selection Policy.

Classifies incoming user intent into optimal candidate tools with
calibrated confidence. Integrates with DeterministicArgumentBuilder.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .artifact import ModelArtifactBundle
from .base import LocalModel, ToolPrediction
from .baseline import TFIDFLogisticBaseline
from .calibration import ConfidenceCalibrator


class ToolPolicyModel(LocalModel):
    """Local policy model predicting tool candidates."""

    def __init__(self, model_id: str = "tool_policy_local", version: str = "v001") -> None:
        super().__init__(target="tool_policy", model_id=model_id, version=version)
        self.calibrator = ConfidenceCalibrator()
        self._baseline_model: TFIDFLogisticBaseline | None = None
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

    def load(self, artifact_dir: Path) -> None:
        """Load and verify model artifact bundle."""
        manifest, vectorizer_data, label_encoder_data, cal_data, _ = (
            ModelArtifactBundle.verify_and_load(artifact_dir, expected_target="tool_policy")
        )
        self.version = manifest.version
        self.model_id = manifest.model_id
        self.calibrator = ConfidenceCalibrator.from_dict(cal_data)

        # Load weights
        weights_path = artifact_dir / "weights.json"
        if weights_path.exists():
            weights_data = json.loads(weights_path.read_text(encoding="utf-8"))
            self._baseline_model = TFIDFLogisticBaseline.from_dict(weights_data)

        self._is_loaded = True

    def predict(self, input_data: dict[str, Any]) -> ToolPrediction:
        """Predict tool name and calibrated confidence."""
        if not self._is_loaded or self._baseline_model is None:
            return ToolPrediction(tool_name="", raw_confidence=0.0, calibrated_confidence=0.0)

        user_input = input_data.get("user_input", "")
        tool_name, raw_conf = self._baseline_model.predict(user_input)
        calibrated_conf = self.calibrator.calibrate(raw_conf)

        meta = self._tool_metadata.get(
            tool_name,
            {"action_type": "execute", "risk_level": "medium", "strategy": "llm_required"},
        )

        return ToolPrediction(
            tool_name=tool_name,
            raw_confidence=raw_conf,
            calibrated_confidence=calibrated_conf,
            action_type=meta.get("action_type", "execute"),
            risk_level=meta.get("risk_level", "medium"),
            argument_strategy=meta.get("strategy", "deterministic"),
            required_context_fields=(),
        )

    def unload(self) -> None:
        self._baseline_model = None
        self._is_loaded = False
