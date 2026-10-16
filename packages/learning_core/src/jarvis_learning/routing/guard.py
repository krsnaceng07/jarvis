"""jarvis_learning.routing.guard — local execution policy safety guard.

Enforces strict safety barriers before any local model prediction can
execute. Destructive operations, shell executions, and file deletions
are NEVER locally executable and are unconditionally delegated to the
foundation reasoning loop.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..models.base import ToolPrediction


@dataclass(frozen=True, slots=True)
class GuardDecision:
    """Outcome of safety policy inspection."""

    allowed: bool
    risk_level: str
    reversibility: str  # "reversible", "idempotent", "irreversible", "destructive"
    reason: str


class LocalDecisionGuard:
    """Pre-execution safety gate for fast-path local tool selection."""

    # Explicit blocklist: tools that modify system state destructively
    DESTRUCTIVE_ACTIONS: set[str] = {
        "system.shell",
        "filesystem.delete",
        "filesystem.overwrite",
        "account.modify",
        "auth.modify",
        "network.policy",
        "channel.send_message",
        "browser.execute_script",
    }

    # Whitelisted low-risk, reversible tools permitted for fast local execution
    SAFE_LOW_RISK_TOOLS: set[str] = {
        "browser.navigate_tab",
        "browser.new_tab",
        "volume.set",
        "volume.mute",
        "system.get_time",
        "app.focus",
    }

    def __init__(self, min_calibrated_confidence: float = 0.85) -> None:
        self.min_calibrated_confidence = min_calibrated_confidence

    def validate(
        self,
        prediction: ToolPrediction,
        context: dict[str, Any] | None = None,
    ) -> GuardDecision:
        """Evaluate whether a local model prediction is safe to execute."""
        tool_name = prediction.tool_name

        # 1. Unconditional block on destructive or sensitive operations
        if tool_name in self.DESTRUCTIVE_ACTIONS or prediction.risk_level == "destructive":
            return GuardDecision(
                allowed=False,
                risk_level="destructive",
                reversibility="destructive",
                reason=f"Tool '{tool_name}' is destructive; requires Foundation LLM reasoning",
            )

        # 2. Risk level checks
        if prediction.risk_level in ("high", "medium"):
            return GuardDecision(
                allowed=False,
                risk_level=prediction.risk_level,
                reversibility="irreversible",
                reason=f"Risk level '{prediction.risk_level}' exceeds local execution limits",
            )

        # 3. Whitelist check for fast-path execution
        if tool_name not in self.SAFE_LOW_RISK_TOOLS:
            return GuardDecision(
                allowed=False,
                risk_level=prediction.risk_level,
                reversibility="unknown",
                reason=f"Tool '{tool_name}' is not in approved local fast-path whitelist",
            )

        # 4. Calibrated confidence threshold check
        if prediction.calibrated_confidence < self.min_calibrated_confidence:
            return GuardDecision(
                allowed=False,
                risk_level=prediction.risk_level,
                reversibility="reversible",
                reason=(
                    f"Calibrated confidence {prediction.calibrated_confidence:.2f} "
                    f"is below required threshold {self.min_calibrated_confidence:.2f}"
                ),
            )

        return GuardDecision(
            allowed=True,
            risk_level="low",
            reversibility="reversible",
            reason="Verified low-risk, reversible, schema-valid action",
        )
